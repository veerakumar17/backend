import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os

# Step 1: Load the dataset
df = pd.read_csv("data/cleane" \
"d_data.csv")
print(f"Dataset loaded: {df.shape[0]} rows, {df.shape[1]} columns")

# Step 2: Handle missing values
df.dropna(inplace=True)
print(f"After dropping nulls: {df.shape[0]} rows")

# Step 3: Separate features and target
X = df.drop(columns=["risk"])
y = df["risk"]
print(f"Features: {list(X.columns)}")
print(f"Target distribution:\n{y.value_counts()}")

# Step 4: Split into train and test sets (80-20)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"\nTraining samples: {len(X_train)}, Testing samples: {len(X_test)}")

# Step 5: Train RandomForestClassifier
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
print("\nModel training complete.")

# Step 6: Evaluate the model using predict (accuracy stays same)
y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)

# Step 7: Print accuracy and classification report
print(f"\nModel Accuracy: {accuracy * 100:.2f}%")
print("\nClassification Report:")
print(classification_report(y_test, y_pred))

# Step 8: Convert to 0-1 float risk score using predict_proba
# Classes are [0, 1, 2] → weights [0.0, 0.5, 1.0]
class_weights = np.array([0.0, 0.5, 1.0])
proba = model.predict_proba(X_test)
risk_scores = proba.dot(class_weights)

# Step 9: Map risk score to Low / Medium / High
def classify_risk(score):
    if score < 0.3:
        return "Low"
    elif score < 0.6:
        return "Medium"
    else:
        return "High"

# Step 10: Show sample risk score outputs
print("\nSample Risk Score Outputs (first 5):")
for i in range(5):
    score = round(risk_scores[i], 4)
    level = classify_risk(score)
    print(f"  Sample {i+1}: risk_score={score} -> {level} Risk")

# Step 11: Save the trained model and feature columns
os.makedirs("model", exist_ok=True)
joblib.dump(model, "model/model.pkl")
joblib.dump(list(X.columns), "model/features.pkl")
print("\nModel saved to model/model.pkl")
print("Features saved to model/features.pkl")
