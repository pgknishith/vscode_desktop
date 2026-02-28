from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# Sample dataset: [Temperature, Humidity, Windy], Target: [Rain (1) or No Rain (0)]
data = [
    [30, 70, 1],  # Hot, Humid, Windy
    [25, 60, 0],  # Warm, Moderate, Not Windy
    [20, 80, 1],  # Cool, Humid, Windy
    [15, 50, 0],  # Cold, Dry, Not Windy
    [35, 90, 1],  # Very Hot, Very Humid, Windy
]
labels = [1, 0, 1, 0, 1]  # Rain or No Rain

# Debug: Check data and labels
assert len(data) == len(labels), "Data and labels must have the same length!"

# Split the data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(data, labels, test_size=0.2, random_state=42)

# Debug: Print training and testing data
print("Training Data:", X_train)
print("Testing Data:", X_test)

# Create and train the Decision Tree Classifier
model = DecisionTreeClassifier()
model.fit(X_train, y_train)

# Make predictions
predictions = model.predict(X_test)

# Evaluate the model
accuracy = accuracy_score(y_test, predictions)
print(f"Model Accuracy: {accuracy * 100:.2f}%")

# Test with new data
new_data = [[28, 65, 0]]  # Example: Warm, Moderate, Not Windy
prediction = model.predict(new_data)
print("Prediction for new data (Rain=1, No Rain=0):", prediction[0])