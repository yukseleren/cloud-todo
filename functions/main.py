import functions_framework
import string

# 1. DEFINE ALPHABETS
# We use all printable characters (digits, letters, punctuation, whitespace)
original_chars = string.printable 
# We reverse them to create a "Substitution Cipher"
cipher_chars = original_chars[::-1]

# 2. CREATE TRANSLATION TABLES
encrypt_table = str.maketrans(original_chars, cipher_chars)
decrypt_table = str.maketrans(cipher_chars, original_chars)

@functions_framework.http
def crypto_handler(request):
    request_json = request.get_json(silent=True)
    
    # FIX: Check for 'text', not 'data' (to match what app.py sends)
    if not request_json or 'text' not in request_json or 'action' not in request_json:
        return {"error": "Missing 'action' or 'text'"}, 400

    action = request_json['action']
    text_data = request_json['text'] 

    try:
        if action == "encrypt":
            return {"result": text_data.translate(encrypt_table)}

        elif action == "decrypt":
            return {"result": text_data.translate(decrypt_table)}
        
        else:
            return {"error": "Invalid action"}, 400

    except Exception as e:
        return {"error": str(e)}, 500