import numpy as np
import cv2

def test_numpy() -> None:
    print("Testing NumPy...")
    arr = np.array([1, 2, 3])
    print(f"Array: {arr}")
    print(f"Mean: {np.mean(arr)}")

def test_opencv() -> None:
    print("\nTesting OpenCV...")
    print(f"OpenCV Version: {cv2.__version__}")
    # Create a small blank image
    img = np.zeros((10, 10, 3))
    print(f"Image shape: {img.shape}")
    
    print("Opening window (might fail on headless systems)...")
    cv2.imshow("Py2Rust OpenCV Test", img)
    cv2.waitKey(1)
    cv2.destroyAllWindows()
    print("OpenCV test complete.")

test_numpy()
test_opencv()
