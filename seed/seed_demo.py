"""Seeds the demo scenario described in the project README:

A customer-support email classifier with three prompt variants (zero-shot,
few-shot, chain-of-thought), run as a live experiment against 500+ synthetic
requests until the statistics engine converges on a winner.

Usage:
    BACKEND_URL=http://localhost:8000 python seed_demo.py
"""
import os
import random
import time
import uuid

import requests

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
N_REQUESTS = int(os.environ.get("SEED_N_REQUESTS", "540"))

EMAIL_TEMPLATES = {
    "billing": [
        "I was charged twice for my {plan} subscription this month, please refund the duplicate charge.",
        "My invoice for {plan} shows the wrong amount, can you correct the billing?",
        "I want to cancel my subscription and get a refund for this billing cycle.",
        "The price on my last payment doesn't match what I signed up for.",
        "Can you send me a copy of my invoice for last month's payment?",
    ],
    "technical": [
        "The app keeps crashing every time I try to open the {feature} screen.",
        "I'm getting an error message when I try to log in to my account.",
        "The {feature} feature is broken and won't load on my phone.",
        "I tried to reset my password but the reset link gives me an error.",
        "There's a bug where the app freezes after I use {feature}.",
    ],
    "account": [
        "How do I change the email address on my account?",
        "I need to update my username, can you help?",
        "Please delete my account and all associated data.",
        "I can't access my account, it says my profile was suspended.",
        "I want to merge two accounts under one username.",
    ],
    "other": [
        "Do you have a referral program for new customers?",
        "What are your customer support hours?",
        "I love the product, just wanted to say thanks!",
        "Do you offer discounts for students?",
        "Where can I find your privacy policy?",
    ],
}

PLANS = ["Pro", "Starter", "Team", "Enterprise"]
FEATURES = ["dashboard", "export", "search", "notifications", "checkout"]


def make_email() -> tuple[str, str]:
    label = random.choice(list(EMAIL_TEMPLATES.keys()))
    template = random.choice(EMAIL_TEMPLATES[label])
    text = template.format(plan=random.choice(PLANS), feature=random.choice(FEATURES))
    return text, label


def wait_for_backend():
    for _ in range(30):
        try:
            r = requests.get(f"{BACKEND_URL}/health", timeout=3)
            if r.ok:
                return
        except requests.RequestException:
            pass
        print("waiting for backend...")
        time.sleep(2)
    raise RuntimeError("Backend never became healthy")


def create_prompt():
    resp = requests.post(
        f"{BACKEND_URL}/prompts",
        json={
            "name": "customer-support-classifier",
            "description": "Classifies inbound support emails into billing/technical/account/other.",
            "actor": "seed_demo",
        },
    )
    if resp.status_code == 400:
        # already exists
        prompts = requests.get(f"{BACKEND_URL}/prompts").json()
        return next(p for p in prompts if p["name"] == "customer-support-classifier")
    resp.raise_for_status()
    return resp.json()


ZERO_SHOT_SYSTEM = """You are a support email classifier. Classify the email below into exactly one \
category: billing, technical, account, or other. Respond with only the category name.

Email: {{email_text}}"""

FEW_SHOT_SYSTEM = """You are a support email classifier. Classify the email below into exactly one \
category: billing, technical, account, or other. Respond with only the category name.

Examples:
- "I was double charged for my plan" -> billing
- "The app crashes on startup" -> technical
- "I need to update my email address" -> account
- "What are your support hours?" -> other

Email: {{email_text}}"""

COT_SYSTEM = """You are a support email classifier. Think step by step about the intent of the email, \
identify key phrases, and then classify it into exactly one category: billing, technical, account, or \
other. First reason about the email, then respond with a final line "category: <label>".

Email: {{email_text}}"""


def create_version(prompt_id, system_prompt, few_shot, commit_message):
    resp = requests.post(
        f"{BACKEND_URL}/prompts/{prompt_id}/versions",
        json={
            "system_prompt": system_prompt,
            "few_shot_examples": few_shot,
            "model_provider": "mock",
            "model_name": "mock-classifier-1",
            "temperature": 0.2,
            "max_tokens": 64,
            "commit_message": commit_message,
            "actor": "seed_demo",
        },
    )
    resp.raise_for_status()
    return resp.json()


def main():
    wait_for_backend()
    prompt = create_prompt()
    prompt_id = prompt["id"]
    print(f"prompt: {prompt_id}")

    v1 = create_version(prompt_id, ZERO_SHOT_SYSTEM, [], "Zero-shot baseline classifier")
    v2 = create_version(
        prompt_id,
        FEW_SHOT_SYSTEM,
        [
            {"user": "I was double charged for my plan", "assistant": "billing"},
            {"user": "The app crashes on startup", "assistant": "technical"},
        ],
        "Few-shot classifier with 2 examples",
    )
    v3 = create_version(prompt_id, COT_SYSTEM, [], "Chain-of-thought classifier")

    experiment_resp = requests.post(
        f"{BACKEND_URL}/experiments",
        json={
            "name": "Support classifier: zero-shot vs few-shot vs CoT",
            "prompt_id": prompt_id,
            "variants": [
                {"version_id": v1["id"], "name": "zero-shot", "traffic_pct": 34, "is_control": True},
                {"version_id": v2["id"], "name": "few-shot", "traffic_pct": 33, "is_control": False},
                {"version_id": v3["id"], "name": "chain-of-thought", "traffic_pct": 33, "is_control": False},
            ],
            "primary_metric": "task_accuracy",
            "target_sample_size": N_REQUESTS,
            "confidence_level": 0.95,
            "auto_promote": True,
            "actor": "seed_demo",
        },
    )
    experiment_resp.raise_for_status()
    experiment = experiment_resp.json()
    experiment_id = experiment["id"]
    print(f"experiment: {experiment_id}")

    start_resp = requests.post(f"{BACKEND_URL}/experiments/{experiment_id}/start")
    start_resp.raise_for_status()
    print("experiment started")

    print(f"sending {N_REQUESTS} synthetic requests...")
    for i in range(N_REQUESTS):
        email_text, label = make_email()
        user_key = str(uuid.uuid4())
        r = requests.post(
            f"{BACKEND_URL}/v1/completions",
            json={
                "prompt_id": prompt_id,
                "variables": {"email_text": email_text},
                "user_key": user_key,
                "expected_label": label,
            },
        )
        if not r.ok:
            print(f"  request {i} failed: {r.status_code} {r.text}")
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{N_REQUESTS} sent")

    print(
        "Done. The worker service will score metrics and check for statistical "
        "significance on its next poll — open the dashboard's Experiments page "
        "to watch it converge."
    )


if __name__ == "__main__":
    main()
