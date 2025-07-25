from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import numpy as np
import tensorflow as tf
import cv2
import os

app = Flask(__name__)

if not os.path.exists('uploads'):
    os.makedirs('uploads')


# Load the pre-trained model
model = tf.keras.models.load_model('./model/deepfake_video_model.h5')

# Define constants
IMG_SIZE = 224
MAX_SEQ_LENGTH = 20
NUM_FEATURES = 2048

#Define the feature extractor (InceptionV3)
def build_feature_extractor():
    feature_extractor = tf.keras.applications.InceptionV3(
        weights="imagenet",
        include_top=False,
        pooling="avg",
        input_shape=(IMG_SIZE, IMG_SIZE, 3),
    )
    preprocess_input = tf.keras.applications.inception_v3.preprocess_input

    inputs = tf.keras.Input((IMG_SIZE, IMG_SIZE, 3))
    preprocessed = preprocess_input(inputs)
    outputs = feature_extractor(preprocessed)

    return tf.keras.Model(inputs, outputs)

feature_extractor = build_feature_extractor()

# Utility function to load and process video
def load_video(path, max_frames=0, resize=(IMG_SIZE, IMG_SIZE)):
    cap = cv2.VideoCapture(path)
    frames = []
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = crop_center_square(frame)
            frame = cv2.resize(frame, resize)
            frame = frame[:, :, [2, 1, 0]]  # Convert BGR to RGB
            frames.append(frame)

            if len(frames) == max_frames:
                break
    finally:
        cap.release()
    return np.array(frames)

# Function to crop the center square of a video frame
def crop_center_square(frame):
    y, x = frame.shape[0:2]
    min_dim = min(y, x)
    start_x = (x // 2) - (min_dim // 2)
    start_y = (y // 2) - (min_dim // 2)
    return frame[start_y : start_y + min_dim, start_x : start_x + min_dim]

def prepare_single_video(frames):
    frames = frames[None, ...]
    frame_mask = np.zeros(shape=(1, MAX_SEQ_LENGTH,), dtype="bool")
    frame_features = np.zeros(shape=(1, MAX_SEQ_LENGTH, NUM_FEATURES), dtype="float32")

    for i, batch in enumerate(frames):
        video_length = batch.shape[0]
        length = min(MAX_SEQ_LENGTH, video_length)
        for j in range(length):
            frame_features[i, j, :] = feature_extractor.predict(batch[None, j, :])
        frame_mask[i, :length] = 1  # 1 = not masked, 0 = masked

    return frame_features, frame_mask

@app.route('/')
def home():
    return render_template('index.html')

# Endpoint to predict if the video is deepfake or not
@app.route('/predict', methods=['POST'])
def predict():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'})

    video = request.files['video']
    if video.filename == '':
        return jsonify({'error': 'No file selected'})

    filename = secure_filename(video.filename)
    app.config['UPLOAD_FOLDER'] = 'uploads'
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    video.save(video_path)

    frames = load_video(video_path)
    frame_features, frame_mask = prepare_single_video(frames)
    prediction = model.predict([frame_features, frame_mask])[0]
    result = 'FAKE' if prediction >= 0.6 else 'REAL'
    confidence = float(prediction)
    os.remove(video_path)

    prediction_msg = f"The video is {result} with {confidence * 100:.2f}% confidence"
    return jsonify({'prediction': prediction_msg, 'filename': filename})



# Function to crop the center square of a video frame
def crop_center_square(frame):
    y, x = frame.shape[0:2]
    min_dim = min(y, x)
    start_x = (x // 2) - (min_dim // 2)
    start_y = (y // 2) - (min_dim // 2)
    return frame[start_y:start_y + min_dim, start_x:start_x + min_dim]

# Create the uploads folder if it doesn’t exist and run the app
if __name__ == '__main__':
    app.run(debug=True)
