import requests
import json

with open(r"C:\\Users\\Admin\\Documents\\2024Hackathon\\kakao\\tokens.json","r") as fp:
    tokens = json.load(fp)
url="https://kapi.kakao.com/v2/api/talk/memo/default/send"

headers={
    "Authorization" : "Bearer " + tokens["access_token"]
}
data={
    "template_object": json.dumps({
        "object_type":"text",
        "text":"Hello, world!"
    })
}

response = requests.post(url, headers=headers, data=data)
response.status_code
print(response.status_code)
if response.json().get('result_code') == 0:
	print('메시지 발송 성공')
else:
	print('메시지 발송 실패\n' + str(response.json()))