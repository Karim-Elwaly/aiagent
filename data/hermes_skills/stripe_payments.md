---
name: stripe_payments
description: Query customers, inspect invoice lifecycle, retrieve payment intent statuses, and reconcile subscription charges.
author: fintech_collective
version: 3.1.0
metadata:
  category: FinTech & Payments
  skills: ['stripe_payments', 'billing_reconcile', 'invoice_check', 'subscription_audit']
  risk_level: medium
parameters:
  resource: { type: string, description: "invoices / customers / payment_intents / subscriptions", required: true }
  customer_id: { type: string, description: "Stripe customer ID (cus_...)", required: false }
  status: { type: string, description: "Filter by status (paid, open, void)", required: false }
---
# Stripe Payments & Invoicing
Query Stripe REST API for billing events, verify checkout completions, and flag delinquent invoices.
