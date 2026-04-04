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

    # Rule-based fallback: salary + risk determines plan
    if risk_level == "Low" and weekly_salary < 3000:
        fallback_plan = "Basic"
    elif risk_level == "High" or weekly_salary >= 5000:
        fallback_plan = "Premium"
    elif risk_level == "Medium" or weekly_salary >= 3000:
        fallback_plan = "Standard"
    else:
        fallback_plan = "Basic"

    prompt = f"""You are an insurance advisor AI for gig delivery workers in India.

User details:
- Weekly Salary: Rs.{weekly_salary}
- Risk Score: {risk_score} ({risk_level} Risk)
- Current Weather Condition: {weather_condition}

Available Plans:
1. Basic Plan   - Weekly Premium: Rs.20, Max Payout: Rs.300  → best for low salary (below Rs.3000/week) and low risk
2. Standard Plan - Weekly Premium: Rs.35, Max Payout: Rs.600  → best for medium salary (Rs.3000–5000/week) or medium risk
3. Premium Plan  - Weekly Premium: Rs.50, Max Payout: Rs.1000 → best for high salary (above Rs.5000/week) or high risk

Rules:
- If salary is low (below Rs.3000) and risk is Low → recommend Basic
- If risk is High or salary is above Rs.5000 → recommend Premium
- Otherwise → recommend Standard
- If weather condition is extreme (Heavy Rain, Extreme Heat, Severe Pollution) → lean toward higher plan

Explain your recommendation in 2–3 simple sentences.
End your response with exactly this line (no extra text after it):
Recommended Plan: <Basic or Standard or Premium>"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=300,
    )

    reply = response.choices[0].message.content.strip()

    recommended_plan = fallback_plan
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
