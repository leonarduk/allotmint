import requests

token = "8491288399:AAGRRuCJtctSQ2igqnW56BxQ3L_c0Jsi_nA"
chat_id = "335560124"
message = "Hello from your PC!"

requests.get(f"https://api.telegram.org/bot{token}/sendMessage", params={
    "chat_id": chat_id,
    "text": message
})
