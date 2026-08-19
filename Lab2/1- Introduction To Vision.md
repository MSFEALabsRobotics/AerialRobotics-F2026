# OpenCV and AirSim Image Processing Tutorial (Python)

This tutorial introduces the main OpenCV operations used for basic image processing and then shows how to display a live camera feed from AirSim.

The tutorial is organized in four parts:

1. OpenCV basics
2. Interactive thresholding with a trackbar
3. HSV color filtering
4. Reading an AirSim camera feed with OpenCV

---

# Part 1 — OpenCV Getting Started

<img width="743" height="500" alt="image" src="https://github.com/user-attachments/assets/a02512b3-1a47-4977-82dc-a8976ee193f8" />

This section shows the most common beginner operations in **cv2** with short code snippets.

---

## 1. Opening an Image
```python
import cv2

img = cv2.imread("image.jpg")   # loads in BGR format
```

---

## 2. Displaying the Image
```python
cv2.imshow("Original", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
```

---

## 3. Displaying the Shape (size)
```python
print("Shape:", img.shape)  # (height, width, channels)
```

---

## 4. Resizing
```python
resized = cv2.resize(img, (300, 200))  # width=300, height=200
cv2.imshow("Resized", resized)
cv2.waitKey(0)
```

---

## 5. Converting to Grayscale
```python
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
cv2.imshow("Gray", gray)
cv2.waitKey(0)
```

---

## 6. Modify One Pixel Value
```python
# Make the pixel at (50, 100) red (BGR format → (0, 0, 255))
img[50, 100] = [0, 0, 255]

cv2.imshow("Modified Pixel", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
```

---

## 7. Saving an Image with imwrite
```python
cv2.imwrite("output_image.jpg", img)
print("Image saved as output_image.jpg")
```

---

## 8. Drawing on the Image
```python
# Copy first
drawn = img.copy()

# Circle (center=(250,150), radius=50)
cv2.circle(drawn, (250,150), 50, (0,255,0), 2)

# Rectangle (top-left, bottom-right)
cv2.rectangle(drawn, (50,50), (200,200), (255,0,0), 2)

# Text
cv2.putText(drawn, "Hello OpenCV", (50, 300),
            cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

cv2.imshow("Drawing", drawn)
cv2.waitKey(0)
```

---

<img width="769" height="563" alt="image" src="https://github.com/user-attachments/assets/b9860776-60f7-483c-b91a-67f100423853" />

## 9. Gaussian Blur
```python
blur = cv2.GaussianBlur(img, (7,7), 1)
cv2.imshow("Blur", blur)
cv2.waitKey(0)
```

---

## 10. Thresholding
```python
_, th = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
cv2.imshow("Threshold", th)
cv2.waitKey(0)
```

---

## 11. Canny Edge Detection
```python
edges = cv2.Canny(gray, 100, 200)
cv2.imshow("Canny Edges", edges)
cv2.waitKey(0)
cv2.destroyAllWindows()
```

---

## 12. Keyboard Interaction
```python
import cv2

gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
cv2.imshow("Keyboard Demo", gray_img)

print("Press 'q' to quit or 's' to save the grayscale image as 'saved_gray.jpg'")

while True:
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):  # Quit on pressing 'q'
        break

    elif key == ord('s'):  # Save the grayscale image on pressing 's'
        cv2.imwrite('saved_gray.jpg', gray_img)
        print("Grayscale image saved as 'saved_gray.jpg'.")

cv2.destroyAllWindows()
```

---

# Part 2 — OpenCV Trackbar Thresholding Demo

This section shows how to use a **trackbar (slider)** in OpenCV to interactively change the threshold value in real time.

---

## Code Example

```python
import cv2

def nothing(x):
    pass

# Load image
img = cv2.imread("image.jpg", 0)  # grayscale

# Create a window
cv2.namedWindow("Trackbar Demo")

# Add a trackbar (name, window, initial value, max value, callback)
cv2.createTrackbar("Thresh", "Trackbar Demo", 128, 255, nothing)

while True:
    # Get current position of the trackbar
    t = cv2.getTrackbarPos("Thresh", "Trackbar Demo")

    # Apply threshold with the trackbar value
    _, th = cv2.threshold(img, t, 255, cv2.THRESH_BINARY)

    # Show the result
    cv2.imshow("Trackbar Demo", th)

    # Break on ESC
    if cv2.waitKey(1) & 0xFF == 27:
        break

cv2.destroyAllWindows()
```

---

## Explanation

- `cv2.createTrackbar(name, window, initial, max, callback)` creates the slider.
- `cv2.getTrackbarPos(name, window)` returns the current slider value.
- We use that value (`t`) as the **threshold** for `cv2.threshold`.
- Press **ESC** to quit the loop.

This way, you can adjust the threshold live and see how the binary image changes.

---

# Part 3 — OpenCV HSV Color Filtering

<img width="557" height="419" alt="image" src="https://github.com/user-attachments/assets/53800889-8c91-47d5-b919-a458afb44523" />

This section shows how to use **HSV color space** in OpenCV to detect and isolate specific colors.

---

## Code Example

```python
import cv2
import numpy as np

# Load image
img = cv2.imread("image.jpg")

# Convert from BGR (default in OpenCV) to HSV
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Define a color range (example: detect blue)
lower_blue = np.array([90, 50, 50])
upper_blue = np.array([140, 255, 255])

# Create a mask (white where blue is found)
mask = cv2.inRange(hsv, lower_blue, upper_blue)

# Apply mask to original image
result = cv2.bitwise_and(img, img, mask=mask)

# Show results
cv2.imshow("Original", img)
cv2.imshow("HSV", hsv)
cv2.imshow("Mask (blue areas)", mask)
cv2.imshow("Result (only blue)", result)

cv2.waitKey(0)
cv2.destroyAllWindows()
```

---

## Explanation

- OpenCV loads images in **BGR** format by default.
- HSV stands for:
  - **H (Hue)** → the color type (0–179 in OpenCV).
  - **S (Saturation)** → intensity or purity of the color.
  - **V (Value)** → brightness of the color.

- `cv2.inRange(hsv, lower, upper)` creates a binary mask where white = pixels inside the range.
- `cv2.bitwise_and(img, img, mask=mask)` applies the mask to the original image.

**Tip:** Adjust the `lower` and `upper` HSV values to detect different colors.

---

# Part 4 — AirSim Camera Feed with OpenCV

The previous sections process images loaded from files. In AirSim, the image can instead come directly from the simulated drone camera.

The following example connects to AirSim, retrieves images from the front-center camera, converts the returned image data into a NumPy array, and displays the camera feed using OpenCV.

---

## Code Example

```python
import airsim
import cv2
import numpy as np

# Replace with Windows host IP
client = airsim.MultirotorClient(ip="WINDOWSIP")
client.confirmConnection()


while True:
    # Get image from front-center camera
    responses = client.simGetImages([
        airsim.ImageRequest("0", airsim.ImageType.Scene, False, False)
    ])

    img1d = np.frombuffer(responses[0].image_data_uint8, dtype=np.uint8)
    img_rgba = img1d.reshape(responses[0].height, responses[0].width, 3)

    cv2.imshow("AirSim Camera", img_rgba)
    cv2.waitKey(1)
```

---

## How the Parts Connect

The OpenCV operations introduced earlier can now be applied to images coming from the AirSim camera.

For example, the same general workflow is:

**Camera/Image → NumPy Array → OpenCV Processing → Display**

This allows the AirSim camera feed to later be used for operations such as:

- Grayscale conversion
- Thresholding
- Edge detection
- HSV color filtering
- Object detection
- Computer vision for drone navigation
