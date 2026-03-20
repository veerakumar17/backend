import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

PLANS = {
    "Basic":    {"weekly_premium": 20,  "max_payout": 300},
    "Standard": {"weekly_premium": 35,  "max_payout": 600},
    "Premium":  {"weekly_premium": 50,  "max_payout": 1000},
}


def get_plan_recommendation(weekly_salary: float, risk_score: float, weather_condition: str) -> dict:
    if risk_score < 0.3:
        risk_level = "Low"
    elif risk_score < 0.6:
        risk_level = "Medium"
    else:
        risk_level = "High"

    prompt = f"""You are an insurance advisor AI.

User details:
- Weekly Salary: {weekly_salary}
- Risk Score: {risk_score} ({risk_level} Risk)
- Weather Condition: {weather_condition}

Available Plans:
1. Basic Plan - Weekly Premium: Rs.20, Max Payout: Rs.300 (low coverage, low cost)
2. Standard Plan - Weekly Premium: Rs.35, Max Payout: Rs.600 (medium coverage)
3. Premium Plan - Weekly Premium: Rs.50, Max Payout: Rs.1000 (high coverage, high cost)

Task:
Suggest the most suitable plan for the user.
Also explain WHY in simple terms.

Keep answer short and clear.
End your response with exactly this line:
Recommended Plan: <plan name>"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=300,
    )

    reply = response.choices[0].message.content.strip()

    recommended_plan = "Standard"
    for plan in PLANS:
        if f"Recommended Plan: {plan}" in reply:
            recommended_plan = plan
            break

    return {
        "recommended_plan": recommended_plan,
        "weekly_premium":   PLANS[recommended_plan]["weekly_premium"],
        "max_payout":       PLANS[recommended_plan]["max_payout"],
        "explanation":      reply,
    }
