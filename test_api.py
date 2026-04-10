# import requests

# API_KEY = "bitmind-81fc1320-2aa4-11f1-b30b-e5a422864534:0ff7c269"

# url = "https://api.bitmind.ai/oracle/v1/34/detect-image"

# headers = {
#     "Authorization": f"Bearer {API_KEY}",
#     "x-bitmind-application": "oracle-api",
#     "Content-Type": "application/json"
# }

# data = {
#     "image": "https://images.unsplash.com/photo-1503023345310-bd7c1de61c7d",
#     "rich": True
# }

# response = requests.post(url, headers=headers, json=data)

# print("Status Code:", response.status_code)
# print("Response:", response.text)

api_user = '341350859'
api_secret = 'BURKJCZSF9q6vNtmQh83SeB2gyXPUqAY'


# this example uses requests
import requests
import json

params = {
  'url': 'https://images.unsplash.com/photo-1503023345310-bd7c1de61c7d',
  'models': 'genai',
  'api_user': {api_user},
  'api_secret': {api_secret}
}
r = requests.get('https://api.sightengine.com/1.0/check.json', params=params)

output = json.loads(r.text)
print(json.dumps(output, indent=2))