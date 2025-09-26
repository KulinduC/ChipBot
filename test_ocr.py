import cv2
import numpy as np
import easyocr

# Plan to preprocess image:
# 1. Maximize text clarity (scaling and contrasting)
# 2. Minimize background interference (color isolation and binarization)
# 3. Clean up noise (blur and morphology)

def text_clarity(image_path):
    img = cv2.imread(image_path)
    # scaled 3x
    scaled = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # Grayscale
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)

    # Adaptive contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray_img = clahe.apply(gray)
    
    candidates = []

    # METHOD 1: OTSU
    _, otsu = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append(('otsu', otsu))

    # METHOD 2: Inverted OTSU
    otsu_inverted = 255 - otsu
    candidates.append(('otsu_inv', otsu_inverted))

    # METHOD 3: Adaptive threshold
    adaptive = cv2.adaptiveThreshold(gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY, 11, 2)
    candidates.append(('adaptive', adaptive))


    # METHOD 4: Multiple fixed thresholds
    for thresh in [150, 180, 200]:
        _, fixed = cv2.threshold(gray_img, thresh, 255, cv2.THRESH_BINARY)
        candidates.append((f'fixed_{thresh}', fixed))

    best,name = best_candidate(candidates)
    cleaned = cleanup_noise(best)

    print(f"Best score using {name} method")

    return cleaned



def best_candidate(candidates):
    best_score = -1
    method = None
    best_result = None
    
    for name, img in candidates:
        score = text_score(img)
        
        if score > best_score:
            best_score = score
            method = name
            best_result = img
    
    return best_result, name

def text_score(binary_img):
    white_pixels = np.sum(binary_img == 255)
    total_pixels = binary_img.size
    white_ratio = white_pixels / total_pixels

    if not (0.01 < white_ratio < 0.4):
        return 0
    
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_img)

    good_components = 0
    for i in range(1, num_labels):  # Skip background (label 0)
        area = stats[i, cv2.CC_STAT_AREA]      # Size of this white blob
        width = stats[i, cv2.CC_STAT_WIDTH]    # Width of this white blob  
        height = stats[i, cv2.CC_STAT_HEIGHT]  # Height of this white blob

        if (30 < area < 8000 and       # Not too tiny, not too huge
        5 < width < 500 and            # Reasonable width  
        8 < height < 150 and           # Reasonable height
        0.1 < width/height < 8):       # Not too skinny/wide
            good_components += 1

    if 2 <= good_components <= 80:
        return good_components * (1 - abs(white_ratio - 0.15))
    else:
        return 0


def cleanup_noise(binary_img):
    # Remove very small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2,2))
    cleaned = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, kernel)
    
    # Fill small gaps in text
    kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel2)
    
    return cleaned

def extract_text(image_path):
    processed_img = text_clarity(image_path)
    
    reader = easyocr.Reader(['en'])
    results = reader.readtext(processed_img)
    
    extracted_text = []
    for (bbox, text, confidence) in results:
        if confidence > 0.5:  # Only keep high-confidence results
            extracted_text.append(text)
    
    return ' '.join(extracted_text)

if __name__ == "__main__":
    text1 = extract_text("images/basketball.png")
    text2 = extract_text("images/burrito.png")
    text3 = extract_text("images/snap.png")
    text4 = extract_text("images/page.png")
    text5 = extract_text("images/cup.png")
    text6 = extract_text("images/bag.png")


    print("Basketball image text:",text1)
    print("Burrito image text:",text2)
    print("Snap image text:",text3)

    print("Paper image text:",text4)
    print("Cup image text:",text5)
    print("Bag image text:",text6)