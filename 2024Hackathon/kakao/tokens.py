import requests

url = 'https://kauth.kakao.com/oauth/token'
rest_api_key = 'd8863805a841dcd49033220b44257e7c'
redirect_uri = 'https://example.com/oauth'
authorize_code = '94T-AjZfz-RUipOyV7lMuc6jrCF8lrNQaiLtLZd_Q2amH2u5Ii5nIgAAAAQKPXRoAAABkMN7F0XGDcCf5rkkeA'

data = {
    'grant_type':'authorization_code',
    'client_id':rest_api_key,
    'redirect_uri':redirect_uri,
    'code': authorize_code,
    }

response = requests.post(url, data=data)
tokens = response.json()
print(tokens)

# json 저장
import json
#1.
with open(r"C:\\Users\\Admin\\Documents\\2024Hackathon\\kakao\\tokens.json","w") as fp:
    json.dump(tokens, fp)