from flask import Flask, request, jsonify
import pickle

app = Flask(__name__)

# Load trained model
model = pickle.load(open("models/NLP_large_model.pkl","rb"))

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.json
        text = data["text"]

        prediction = model.predict([text])[0]

        probability_fake = model.predict_proba([text])[0][0]

        return jsonify({
            "prediction": int(prediction),
            "probability": float(probability_fake)
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500
    
if __name__ == "__main__":
    app.run(port=5000)
    print("Server is running on http://localhost:5000")