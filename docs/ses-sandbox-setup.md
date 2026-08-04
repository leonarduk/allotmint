# AWS SES Sandbox Setup for Signup Emails

The signup flow (`backend/routes/signup.py`, `backend/emails/signup_request.py`,
`backend/emails/signup_approved.py`) sends email via AWS SES. A new AWS
account's SES access starts in **sandbox mode**, which only allows sending to
verified identities. Deploying the signup flow without verifying the relevant
addresses first causes SES to reject every email with a `MessageRejected`
error, and the affected requests will silently never notify anyone.

## Addresses that must be verified

While the SES account is in sandbox mode, verify:

- `SIGNUP_ADMIN_EMAIL` — receives the admin notification email for every new
  signup request (sent by `send_signup_admin_email` in
  `backend/emails/signup_request.py`).
- Each visitor email address that will receive the "your login is ready"
  email after approval (sent by `send_signup_approved_email` in
  `backend/emails/signup_approved.py`). In sandbox mode this means every
  visitor who signs up must also be a verified SES identity — acceptable for
  testing with a handful of known addresses, but not for public production
  traffic.

## How to verify an address

1. AWS Console → **SES** → **Verified identities** → **Create identity**.
2. Choose **Email address**, enter the address, and confirm the verification
   link sent to that inbox.
3. Repeat for `SIGNUP_ADMIN_EMAIL` and any other addresses you need to test
   with while still in sandbox mode.

## Moving out of sandbox mode

To send to arbitrary visitor addresses without verifying each one first,
request SES production access (AWS Console → SES → Account dashboard →
**Request production access**). This is out of scope for the signup flow's
own code and is a one-time AWS account setup step.
