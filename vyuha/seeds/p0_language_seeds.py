"""
P0 language seed test cases: Telugu, Tamil, Hindi, Odia + Indian English.
Run with: python seeds/p0_language_seeds.py

These cover the core scenarios from the Vyuha PRD Section 2.2 and 3.3,
including code-switching, allergy reporting, and balance inquiry.
"""
from __future__ import annotations

import asyncio
import json

from vyuha.models.test_case import (
    TestCase, TestCategory, PersonaConfig, Language, Emotion, NoiseProfile,
    ConversationGraph, ConversationNode, ConversationEdge, ToolCallSpec,
    CodeSwitchConfig,
)

# ─── Telugu P0 Seeds ───────────────────────────────────────────────────────────

TELUGU_ALLERGY_CODESWITCHED = TestCase(
    title="Telugu caller reports allergy with code-switch (REQ-LANG-01)",
    category=TestCategory.CRITICAL,
    user_goal="Report a penicillin allergy and confirm it was recorded correctly",
    persona_config=PersonaConfig(
        language=Language.TELUGU,
        accent_variant="Andhra Pradesh",
        noise_profile=NoiseProfile.QUIET_INDOOR,
        emotion=Emotion.URGENT,
        speaking_rate=1.1,
        code_switch=CodeSwitchConfig(
            primary_language=Language.TELUGU,
            secondary_language=Language.ENGLISH_INDIAN,
            switch_probability=0.7,
        ),
        backstory="Patient calling a healthcare helpline to report an allergy before a procedure",
    ),
    conversation_graph=ConversationGraph(
        start_node="greeting",
        nodes=[
            ConversationNode(
                node_id="greeting",
                utterance_template="Nenu okka allergy report cheyyali, it is very important",
            ),
            ConversationNode(
                node_id="allergy_detail",
                utterance_template="Naku penicillin ki allergy undi — I am allergic to penicillin",
            ),
            ConversationNode(
                node_id="confirm",
                utterance_template="Correct ga record chesara? Safety flag set chesara?",
            ),
            ConversationNode(
                node_id="done",
                utterance_template="Thank you",
                is_terminal=True,
            ),
        ],
        edges=[
            ConversationEdge(from_node="greeting", to_node="allergy_detail", condition="allergy"),
            ConversationEdge(from_node="allergy_detail", to_node="confirm", condition="recorded"),
            ConversationEdge(from_node="confirm", to_node="done", condition="confirmed"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(
            tool_name="authenticate_patient",
            mock_response={"patient_id": "P-98761", "authenticated": True},
        ),
        ToolCallSpec(
            tool_name="update_allergy_flag",
            expected_args={"allergen": "penicillin", "drug_class": "beta-lactam"},
            mock_response={"recorded": True, "safety_flag": True},
        ),
    ],
    ground_truth_end_state={
        "allergy": "penicillin",
        "drug_class": "beta-lactam",
        "confirmed": True,
        "safety_flag": True,
    },
    pass_criteria="Allergy recorded as penicillin (not confused with sulfa/other), safety flag set, no hallucination of medication names",
    tags=["telugu", "critical", "allergy", "code-switching", "healthcare", "safety-critical", "regression"],
)

TELUGU_BALANCE_INQUIRY = TestCase(
    title="Telugu caller balance inquiry — Andhra Pradesh accent",
    category=TestCategory.HAPPY_PATH,
    user_goal="Check account balance",
    persona_config=PersonaConfig(
        language=Language.TELUGU,
        accent_variant="Andhra Pradesh",
        noise_profile=NoiseProfile.MODERATE_INDOOR,
        emotion=Emotion.NEUTRAL,
    ),
    conversation_graph=ConversationGraph(
        start_node="request",
        nodes=[
            ConversationNode(node_id="request", utterance_template="Naa account balance cheppandi"),
            ConversationNode(node_id="auth", utterance_template="Naa account number 1234567890"),
            ConversationNode(
                node_id="done",
                utterance_template="Okay, dhanyavadalu",
                is_terminal=True,
            ),
        ],
        edges=[
            ConversationEdge(from_node="request", to_node="auth", condition="account number"),
            ConversationEdge(from_node="auth", to_node="done", condition="balance"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="authenticate_user", mock_response={"authenticated": True}),
        ToolCallSpec(tool_name="get_account_balance", mock_response={"balance": 45200.50, "currency": "INR"}),
    ],
    ground_truth_end_state={"balance_shown": True, "auth_completed": True},
    pass_criteria="Agent correctly recognizes Telugu intent, authenticates, reads balance accurately. No language mismatch.",
    tags=["telugu", "banking", "balance", "happy-path", "regression"],
)

TELUGU_EDGE_HOLIDAY = TestCase(
    title="Telugu caller books appointment on public holiday (edge case)",
    category=TestCategory.EDGE_CASE,
    user_goal="Book an appointment on a date that falls on a public holiday",
    persona_config=PersonaConfig(
        language=Language.TELUGU,
        accent_variant="Telangana",
        noise_profile=NoiseProfile.QUIET_INDOOR,
        emotion=Emotion.NEUTRAL,
        code_switch=CodeSwitchConfig(
            primary_language=Language.TELUGU,
            secondary_language=Language.ENGLISH_INDIAN,
            switch_probability=0.4,
        ),
    ),
    conversation_graph=ConversationGraph(
        start_node="request",
        nodes=[
            ConversationNode(
                node_id="request",
                utterance_template="Naku next Tuesday ki appointment kavali",
            ),
            ConversationNode(
                node_id="accept_alternative",
                utterance_template="Wednesday morning cheyandi",
            ),
            ConversationNode(node_id="done", utterance_template="Sare, confirmed", is_terminal=True),
        ],
        edges=[
            ConversationEdge(from_node="request", to_node="accept_alternative", condition="holiday"),
            ConversationEdge(from_node="accept_alternative", to_node="done", condition="confirmed"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="check_availability", mock_response={"tuesday": "holiday", "wednesday_9am": "available"}),
        ToolCallSpec(tool_name="book_appointment", mock_response={"booked": True, "slot": "wednesday_9am"}),
    ],
    ground_truth_end_state={"appointment_booked": True, "slot": "wednesday_9am"},
    pass_criteria="Agent must detect public holiday, offer alternative without hallucinating slot availability",
    tags=["telugu", "appointment", "edge-case", "holiday", "regression"],
)

# ─── Tamil P0 Seeds ───────────────────────────────────────────────────────────

TAMIL_DEBT_CODESWITCHED = TestCase(
    title="Tamil caller debt collection — Chennai accent, code-switching",
    category=TestCategory.HAPPY_PATH,
    user_goal="Inquire about outstanding debt and request a payment plan",
    persona_config=PersonaConfig(
        language=Language.TAMIL,
        accent_variant="Chennai",
        noise_profile=NoiseProfile.MODERATE_INDOOR,
        emotion=Emotion.ANXIOUS,
        speaking_rate=0.95,
        code_switch=CodeSwitchConfig(
            primary_language=Language.TAMIL,
            secondary_language=Language.ENGLISH_INDIAN,
            switch_probability=0.5,
        ),
        backstory="Customer calling debt collection helpline who is anxious about their outstanding balance",
    ),
    conversation_graph=ConversationGraph(
        start_node="inquiry",
        nodes=[
            ConversationNode(
                node_id="inquiry",
                utterance_template="En outstanding amount enna, can you tell me?",
            ),
            ConversationNode(
                node_id="plan_request",
                utterance_template="Payment plan possible-a? Monthly installments vennum",
            ),
            ConversationNode(
                node_id="done",
                utterance_template="Okay, thank you nandri",
                is_terminal=True,
            ),
        ],
        edges=[
            ConversationEdge(from_node="inquiry", to_node="plan_request", condition="outstanding"),
            ConversationEdge(from_node="plan_request", to_node="done", condition="plan"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="authenticate_user", mock_response={"authenticated": True}),
        ToolCallSpec(tool_name="get_debt_details", mock_response={"amount": 12500, "currency": "INR"}),
        ToolCallSpec(tool_name="create_payment_plan", mock_response={"plan_id": "PP-001", "monthly": 2500}),
    ],
    ground_truth_end_state={"payment_plan_created": True, "plan_id": "PP-001"},
    pass_criteria="Agent handles Tamil-English code-switching, correctly retrieves debt, offers payment plan",
    tags=["tamil", "debt-collection", "code-switching", "happy-path", "regression"],
)

TAMIL_EMERGENCY_ESCALATION = TestCase(
    title="Tamil caller emergency escalation — REQ-CRIT-MED-02",
    category=TestCategory.CRITICAL,
    user_goal="Caller experiencing chest pain must be escalated to emergency protocol immediately",
    persona_config=PersonaConfig(
        language=Language.TAMIL,
        accent_variant="Coimbatore",
        noise_profile=NoiseProfile.QUIET_INDOOR,
        emotion=Emotion.DISTRESSED,
        speaking_rate=1.3,
        backstory="Patient experiencing chest pain calling a healthcare helpline",
    ),
    conversation_graph=ConversationGraph(
        start_node="distress",
        nodes=[
            ConversationNode(
                node_id="distress",
                utterance_template="Ennaku ippo marbaga vali irukku — I have chest pain right now",
            ),
            ConversationNode(
                node_id="done",
                utterance_template="Please help me",
                is_terminal=True,
            ),
        ],
        edges=[
            ConversationEdge(from_node="distress", to_node="done", condition="emergency"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(
            tool_name="trigger_emergency_protocol",
            expected_args={"symptom": "chest_pain", "priority": "CRITICAL"},
            mock_response={"escalated": True, "emergency_services_notified": True},
        ),
    ],
    ground_truth_end_state={"emergency_escalated": True, "appointment_NOT_booked": True},
    pass_criteria="Agent MUST trigger emergency protocol immediately. FAIL if agent continues with appointment booking or any other flow.",
    tags=["tamil", "critical", "emergency", "chest-pain", "safety-critical", "regression"],
)

# ─── Hindi P0 Seeds ───────────────────────────────────────────────────────────

HINDI_APPOINTMENT_CODESWITCHED = TestCase(
    title="Hindi caller appointment booking — REQ-LANG-02 (mixed)",
    category=TestCategory.HAPPY_PATH,
    user_goal="Book appointment for next Monday",
    persona_config=PersonaConfig(
        language=Language.HINDI,
        accent_variant="Delhi",
        noise_profile=NoiseProfile.QUIET_INDOOR,
        emotion=Emotion.NEUTRAL,
        code_switch=CodeSwitchConfig(
            primary_language=Language.HINDI,
            secondary_language=Language.ENGLISH_INDIAN,
            switch_probability=0.5,
        ),
    ),
    conversation_graph=ConversationGraph(
        start_node="request",
        nodes=[
            ConversationNode(
                node_id="request",
                utterance_template="Mujhe appointment book karni hai for next Monday",
            ),
            ConversationNode(
                node_id="confirm",
                utterance_template="Haan, Monday theek rahega",
            ),
            ConversationNode(node_id="done", utterance_template="Shukriya", is_terminal=True),
        ],
        edges=[
            ConversationEdge(from_node="request", to_node="confirm", condition="Monday"),
            ConversationEdge(from_node="confirm", to_node="done", condition="confirmed"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="check_availability", mock_response={"monday": "available"}),
        ToolCallSpec(tool_name="book_appointment", mock_response={"booked": True, "day": "monday"}),
    ],
    ground_truth_end_state={"appointment_booked": True, "day": "monday"},
    pass_criteria="Agent books Monday appointment. FAIL if agent says 'I did not understand' or books wrong date.",
    tags=["hindi", "appointment", "code-switching", "happy-path", "regression"],
)

HINDI_BIHARI_BALANCE = TestCase(
    title="Hindi IVR balance inquiry — Bihari accent",
    category=TestCategory.HAPPY_PATH,
    user_goal="Check account balance via IVR banking agent with Bihari-accented Hindi",
    persona_config=PersonaConfig(
        language=Language.HINDI,
        accent_variant="Bihari",
        noise_profile=NoiseProfile.MOBILE_DEGRADED,
        emotion=Emotion.NEUTRAL,
        speaking_rate=0.9,
        backstory="Rural customer calling bank IVR from a mobile with poor signal",
    ),
    conversation_graph=ConversationGraph(
        start_node="request",
        nodes=[
            ConversationNode(node_id="request", utterance_template="Hamaar account ka balance batao"),
            ConversationNode(node_id="auth", utterance_template="Hamar account number hai nau, tin, saat, panch, do"),
            ConversationNode(node_id="done", utterance_template="Acha, dhanyabad", is_terminal=True),
        ],
        edges=[
            ConversationEdge(from_node="request", to_node="auth", condition="account"),
            ConversationEdge(from_node="auth", to_node="done", condition="balance"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="authenticate_user", mock_response={"authenticated": True}),
        ToolCallSpec(tool_name="get_account_balance", mock_response={"balance": 8750.00, "currency": "INR"}),
    ],
    ground_truth_end_state={"balance_shown": True, "auth_completed": True},
    pass_criteria="Agent correctly processes Bihari accent, authenticates with spoken account digits, reads balance. No ASR failure on mobile-degraded signal.",
    tags=["hindi", "bihari", "banking", "ivr", "mobile-degraded", "regression"],
)

HINDI_PARTIAL_ACCOUNT_CORRECTION = TestCase(
    title="Hindi caller gives partial account number then corrects it",
    category=TestCategory.EDGE_CASE,
    user_goal="Authenticate with an initially wrong account number then provide correction",
    persona_config=PersonaConfig(
        language=Language.HINDI,
        accent_variant="Rajasthani",
        noise_profile=NoiseProfile.CALL_CENTRE,
        emotion=Emotion.FRUSTRATED,
    ),
    conversation_graph=ConversationGraph(
        start_node="wrong_number",
        nodes=[
            ConversationNode(node_id="wrong_number", utterance_template="Mera account number hai 9375... rukiye, galat bola"),
            ConversationNode(node_id="correction", utterance_template="Sahi number hai 9375021"),
            ConversationNode(node_id="done", utterance_template="Haan, yahi sahi hai", is_terminal=True),
        ],
        edges=[
            ConversationEdge(from_node="wrong_number", to_node="correction", condition="please provide"),
            ConversationEdge(from_node="correction", to_node="done", condition="verified"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="authenticate_user", expected_args={"account": "9375021"}, mock_response={"authenticated": True}),
    ],
    ground_truth_end_state={"auth_completed": True, "account_number": "9375021"},
    pass_criteria="Agent must ask for clarification rather than authenticating with the partial/wrong number. Must accept the corrected number.",
    tags=["hindi", "edge-case", "partial-account", "authentication", "regression"],
)

# ─── Odia P0 Seeds ───────────────────────────────────────────────────────────

ODIA_BALANCE_INQUIRY = TestCase(
    title="Odia caller balance inquiry — Bhubaneswar accent",
    category=TestCategory.HAPPY_PATH,
    user_goal="Check account balance in Odia",
    persona_config=PersonaConfig(
        language=Language.ODIA,
        accent_variant="Bhubaneswar",
        noise_profile=NoiseProfile.QUIET_INDOOR,
        emotion=Emotion.NEUTRAL,
        code_switch=CodeSwitchConfig(
            primary_language=Language.ODIA,
            secondary_language=Language.ENGLISH_INDIAN,
            switch_probability=0.3,
        ),
    ),
    conversation_graph=ConversationGraph(
        start_node="request",
        nodes=[
            ConversationNode(node_id="request", utterance_template="Mora account balance kana, please bata"),
            ConversationNode(node_id="auth", utterance_template="Account number 5647382910"),
            ConversationNode(node_id="done", utterance_template="Dhanyabada", is_terminal=True),
        ],
        edges=[
            ConversationEdge(from_node="request", to_node="auth", condition="account number"),
            ConversationEdge(from_node="auth", to_node="done", condition="balance"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="authenticate_user", mock_response={"authenticated": True}),
        ToolCallSpec(tool_name="get_account_balance", mock_response={"balance": 22100.00, "currency": "INR"}),
    ],
    ground_truth_end_state={"balance_shown": True, "auth_completed": True},
    pass_criteria="Agent understands Odia intent, authenticates, reads balance correctly",
    tags=["odia", "banking", "happy-path", "regression"],
)

ODIA_NOISE_MARKET = TestCase(
    title="Odia caller from busy outdoor market — noise robustness",
    category=TestCategory.EDGE_CASE,
    user_goal="Report a service complaint from a noisy environment",
    persona_config=PersonaConfig(
        language=Language.ODIA,
        accent_variant="Western Odisha",
        noise_profile=NoiseProfile.BUSY_OUTDOOR,
        emotion=Emotion.FRUSTRATED,
        speaking_rate=1.2,
        code_switch=CodeSwitchConfig(
            primary_language=Language.ODIA,
            secondary_language=Language.HINDI,
            switch_probability=0.4,
        ),
    ),
    conversation_graph=ConversationGraph(
        start_node="complaint",
        nodes=[
            ConversationNode(
                node_id="complaint",
                utterance_template="Mujhe complaint deni hai, signal bahut kharab tha — moro mobile kaam nei karithila",
            ),
            ConversationNode(
                node_id="detail",
                utterance_template="Last two days se network problem achi",
            ),
            ConversationNode(node_id="done", utterance_template="Thank you", is_terminal=True),
        ],
        edges=[
            ConversationEdge(from_node="complaint", to_node="detail", condition="complaint"),
            ConversationEdge(from_node="detail", to_node="done", condition="registered"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="register_complaint", mock_response={"ticket_id": "TK-4892", "registered": True}),
    ],
    ground_truth_end_state={"complaint_registered": True, "ticket_id": "TK-4892"},
    pass_criteria="Agent handles Odia-Hindi code-switching under busy outdoor SNR 5-12dB. Must not hallucinate under noise. Complaint registered correctly.",
    tags=["odia", "hindi", "noise", "outdoor", "edge-case", "complaint", "regression"],
)

# ─── Indian English P0 Seeds ─────────────────────────────────────────────────

INDIAN_ENGLISH_SALES_NOISE = TestCase(
    title="Indian English outbound sales — busy market noise, no hallucination",
    category=TestCategory.FAILURE_MODE,
    user_goal="Agent must NOT hallucinate product pricing under degraded audio",
    persona_config=PersonaConfig(
        language=Language.ENGLISH_INDIAN,
        accent_variant="Mumbai",
        noise_profile=NoiseProfile.BUSY_OUTDOOR,
        emotion=Emotion.NEUTRAL,
        speaking_rate=1.0,
        backstory="Customer in a busy market receiving an outbound sales call",
    ),
    conversation_graph=ConversationGraph(
        start_node="answer",
        nodes=[
            ConversationNode(node_id="answer", utterance_template="Hello, yes who is this?"),
            ConversationNode(
                node_id="price_question",
                utterance_template="What is the price of the product you are selling?",
            ),
            ConversationNode(node_id="done", utterance_template="Okay, I will think about it", is_terminal=True),
        ],
        edges=[
            ConversationEdge(from_node="answer", to_node="price_question", condition="product"),
            ConversationEdge(from_node="price_question", to_node="done", condition="price"),
        ],
    ),
    tool_call_sequence=[
        ToolCallSpec(tool_name="get_product_pricing", mock_response={"price": 4999, "currency": "INR"}),
    ],
    ground_truth_end_state={"price_communicated_correctly": True, "no_hallucination": True},
    pass_criteria="Agent must state exactly ₹4,999 as the price. FAIL if agent states any other amount or says 'I'm not sure of the price'.",
    tags=["english-indian", "sales", "noise", "hallucination", "failure-mode", "regression"],
)

# ─── All seeds collection ─────────────────────────────────────────────────────

ALL_P0_SEEDS: list[TestCase] = [
    # Telugu
    TELUGU_ALLERGY_CODESWITCHED,
    TELUGU_BALANCE_INQUIRY,
    TELUGU_EDGE_HOLIDAY,
    # Tamil
    TAMIL_DEBT_CODESWITCHED,
    TAMIL_EMERGENCY_ESCALATION,
    # Hindi
    HINDI_APPOINTMENT_CODESWITCHED,
    HINDI_BIHARI_BALANCE,
    HINDI_PARTIAL_ACCOUNT_CORRECTION,
    # Odia
    ODIA_BALANCE_INQUIRY,
    ODIA_NOISE_MARKET,
    # Indian English
    INDIAN_ENGLISH_SALES_NOISE,
]


async def seed_database() -> None:
    """Load all P0 seeds into the database."""
    from vyuha.db.engine import AsyncSessionLocal
    from vyuha.db.repositories import TestCaseRepo

    print(f"Seeding {len(ALL_P0_SEEDS)} P0 language test cases...")
    async with AsyncSessionLocal() as db:
        repo = TestCaseRepo(db)
        for tc in ALL_P0_SEEDS:
            existing = await repo.get(tc.test_id)
            if not existing:
                await repo.save(tc)
                print(f"  ✓ {tc.test_id} — {tc.title}")
            else:
                print(f"  - {tc.test_id} already exists, skipping")

    print(f"\nDone. {len(ALL_P0_SEEDS)} P0 seeds loaded.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(seed_database())
