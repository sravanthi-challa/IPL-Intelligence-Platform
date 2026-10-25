import os
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

SYSTEM_PROMPT = """You are IPL Intelligence, a premier AI cricket analytics platform.
Answer the user's question strictly using the provided VERIFIED DATABASE SQL RESULTS and RETRIEVED CRICKET EVIDENCE.

CRITICAL GROUNDING RULES:
1. Ground every single claim in the supplied evidence. Explicitly cite sources by their Document ID (e.g., [Doc: match_335982] or [Doc: dict_bowling_metrics]).
2. NEVER invent, extrapolate, or hallucinate cricket statistics, match outcomes, player numbers, or dates.
3. If the provided evidence is insufficient or does not mention the answer, state clearly: "The available IPL database and retrieved documents do not contain sufficient evidence to answer this question."
4. Treat VERIFIED DATABASE SQL RESULTS as the ultimate ground truth for all numerical facts.
5. Clearly distinguish retrieved historical facts from analytical commentary.
"""

class BaseLLMClient(ABC):
    @abstractmethod
    def generate(self, user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        pass

class OpenAILLMClient(BaseLLMClient):
    """
    OpenAI API client supporting models like gpt-4o-mini, gpt-4o.
    """
    def __init__(self, model: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self.model = model
        api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)

    def generate(self, user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # Low temperature for strict factual grounding
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()

class OfflineGroundedGenerator(BaseLLMClient):
    """
    Zero-cost deterministic factual generator for offline testing and environments
    without external API keys. Extracts verified answers and citations directly
    from the provided context blocks.
    """
    @staticmethod
    def _format_sql_evidence(sql_text: str) -> str:
        lines = [l.strip() for l in sql_text.strip().split("\n") if l.strip()]
        if not lines:
            return sql_text

        # Check for bowling leaderboard
        if any("wickets:" in l for l in lines) and any("player_name:" in l for l in lines):
            parsed = []
            for l in lines:
                parts = dict(re.findall(r"(\w+):\s*([^,]+)", l))
                if parts:
                    parsed.append(parts)
            if parsed:
                top = parsed[0]
                summary = [f"🏆 **{top.get('player_name', 'Unknown')}** is the all-time leading wicket-taker in IPL history with **{top.get('wickets', '')} wickets** in {top.get('matches_bowled', '')} matches (Economy: {top.get('economy_rate', '')}, Average: {top.get('bowling_average', '')})."]
                if len(parsed) > 1:
                    summary.append("\n**Top Contenders:**")
                    for p in parsed[1:6]:
                        summary.append(f"- **{p.get('player_name')}**: {p.get('wickets')} wickets (Econ: {p.get('economy_rate')}, Avg: {p.get('bowling_average')})")
                return "\n".join(summary)

        # Check for batting leaderboard
        if any("total_runs:" in l for l in lines) and any("player_name:" in l or "batter_name:" in l for l in lines):
            parsed = []
            for l in lines:
                parts = dict(re.findall(r"(\w+):\s*([^,]+)", l))
                if parts:
                    parsed.append(parts)
            if parsed:
                top = parsed[0]
                name = top.get('player_name') or top.get('batter_name')
                summary = [f"🏆 **{name}** leads the scoring with **{top.get('total_runs', '')} runs** (Strike Rate: {top.get('strike_rate', '')}, Fours: {top.get('fours', '0')}, Sixes: {top.get('sixes', '0')})."]
                if len(parsed) > 1:
                    summary.append("\n**Top Contenders:**")
                    for p in parsed[1:6]:
                        pname = p.get('player_name') or p.get('batter_name')
                        summary.append(f"- **{pname}**: {p.get('total_runs')} runs (SR: {p.get('strike_rate')})")
                return "\n".join(summary)

        # Check for Head to Head
        if any("team1_wins:" in l for l in lines) and any("team2_wins:" in l for l in lines):
            parts = dict(re.findall(r"(\w+):\s*([^,\n]+)", sql_text))
            t1 = parts.get("team1", "Team 1")
            t2 = parts.get("team2", "Team 2")
            w1 = parts.get("team1_wins", "0")
            w2 = parts.get("team2_wins", "0")
            tot = parts.get("total_matches", "0")
            return f"Across **{tot} matches** between **{t1}** and **{t2}**:\n- **{t1}**: {w1} wins\n- **{t2}**: {w2} wins"

        # Default clean bullet formatting for any other SQL rows
        clean_lines = []
        for l in lines[:6]:
            clean = re.sub(r"^Row \d+:\s*", "- ", l)
            clean_lines.append(clean)
        return "\n".join(clean_lines)

    def generate(self, user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        # Check if context contains evidence
        if "=== RETRIEVED CRICKET EVIDENCE ===" not in user_prompt and "=== VERIFIED DATABASE SQL RESULTS ===" not in user_prompt:
            return "The available IPL database and retrieved documents do not contain sufficient evidence to answer this question."

        # Extract evidence blocks
        blocks = re.findall(r"\[Evidence Block \d+\]\s+Document ID:\s+([^\n]+)\s+Title:\s+([^\n]+)\s+Content:\s+(.+?)(?=\[Evidence Block|\=\=\=|$)", user_prompt, re.DOTALL)
        sql_match = re.search(r"=== VERIFIED DATABASE SQL RESULTS ===\n(.*?)\n=====================================", user_prompt, re.DOTALL)

        response_parts = []

        if sql_match:
            sql_text = sql_match.group(1).strip()
            formatted_sql = self._format_sql_evidence(sql_text)
            response_parts.append(f"{formatted_sql}\n\n[Source: PostgreSQL Analytics Engine]")

        if blocks:
            for doc_id, title, content in blocks[:2]:
                first_lines = "\n".join([line for line in content.strip().split("\n") if line.strip()][:4])
                response_parts.append(f"According to {title} ([Doc: {doc_id.strip()}]):\n{first_lines}")

        if not response_parts:
            return "The available IPL database and retrieved documents do not contain sufficient evidence to answer this question."

        return "\n\n".join(response_parts)

class RAGGenerator:
    """
    Orchestrates grounded answer generation using the configured LLM client.
    """
    def __init__(self, client: Optional[BaseLLMClient] = None):
        if client:
            self.client = client
        else:
            provider = os.environ.get("LLM_PROVIDER", "").lower()
            api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if provider == "openai" and api_key and not api_key.startswith("your_"):
                model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
                self.client = OpenAILLMClient(model=model, api_key=api_key)
            else:
                self.client = OfflineGroundedGenerator()

    def generate_answer(
        self,
        question: str,
        context_text: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        prompt_parts = []
        if conversation_history:
            prompt_parts.append("CONVERSATION HISTORY:")
            for turn in conversation_history[-4:]:
                prompt_parts.append(f"{turn['role'].upper()}: {turn['content']}")
            prompt_parts.append("")

        prompt_parts.append("EVIDENCE CONTEXT:")
        prompt_parts.append(context_text if context_text.strip() else "[NO RELEVANT EVIDENCE RETRIEVED]")
        prompt_parts.append("")
        prompt_parts.append(f"USER QUESTION: {question}")
        prompt_parts.append("GROUNDED ANSWER:")

        user_prompt = "\n".join(prompt_parts)
        return self.client.generate(user_prompt)
