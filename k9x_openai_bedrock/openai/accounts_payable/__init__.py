# SPDX-License-Identifier: Apache-2.0
"""
Accounts payable demo (use case 3 on openai.k9x.ai): OpenAI agents run by a K9-AIF squad, a decision from the
K9X Rules Engine (currently GoRules), and a person's approval in K9X HIL when the rules ask for one.

Flow: Router -> Kafka (openai.ap.in) -> APOrchestrator -> squad ap_invoice:
  1. InvoiceAgent (OpenAI agent, structured output): reads the invoice, looks up the vendor and the invoice record
  2. APRulesAgent (K9RulesAgent -> GoRulesAdapter): AP-01..AP-08 decide reject / auto_pay / needs_approval
  3. PaymentAgent (OpenAI agent): pays; pay_invoice pauses for a person only when the rules said needs_approval
The pause goes to K9X HIL over Kafka (hil.requests.openai-ap-payments); the decision comes back on
hil.replies.openai-ap-payments, the Router resumes the flow, and the same OpenAI run continues.
"""
