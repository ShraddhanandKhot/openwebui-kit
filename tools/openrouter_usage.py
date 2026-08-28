import os
import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        OPENROUTER_API_KEY: str = Field(
            default="",
            description="Your OpenRouter API Key. If left empty, it will try to use the system OPENROUTER_API_KEY environment variable.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def get_openrouter_key_status(self) -> str:
        """
        Check the current OpenRouter API key status, including credit limits, usage, and remaining balance.
        :return: String formatted summary of the OpenRouter account/key usage.
        """
        # Determine API Key to use
        api_key = self.valves.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")

        if not api_key:
            return "Error: No OpenRouter API key provided in Tool Valves or environment variables."

        url = "https://openrouter.ai/api/v1/key"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://openwebui.com",
            "X-Title": "Open WebUI",
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json().get("data", {})

                label = data.get("label", "N/A")
                usage = data.get("usage", 0.0)
                limit = data.get("limit")
                limit_remaining = data.get("limit_remaining")
                is_free_tier = data.get("is_free_tier", False)

                limit_str = f"${limit:.4f}" if limit is not None else "Unlimited"
                remaining_str = (
                    f"${limit_remaining:.4f}"
                    if limit_remaining is not None
                    else "Unlimited"
                )

                output = (
                    f"**OpenRouter Key Status**\n"
                    f"- **Key Label:** {label}\n"
                    f"- **Total Usage:** ${usage:.4f}\n"
                    f"- **Key Credit Limit:** {limit_str}\n"
                    f"- **Remaining Credits:** {remaining_str}\n"
                    f"- **Free Tier Account:** {is_free_tier}\n"
                )
                return output
            elif response.status_code == 401:
                return "Error: Invalid OpenRouter API Key."
            else:
                return f"Error fetching OpenRouter status: HTTP {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error executing OpenRouter key check: {str(e)}"
