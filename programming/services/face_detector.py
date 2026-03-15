import time
import base64
import logging

from django.conf import settings

logger = logging.getLogger('programming')

OPENCV_AVAILABLE = False
cv2 = None
np = None

try:
    import cv2 as _cv2
    import numpy as _np
    cv2 = _cv2
    np = _np
    OPENCV_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ OpenCV / numpy 未安装，人脸检测功能不可用。")
except Exception as e:
    logger.error(f"⚠️ OpenCV 初始化失败：{e}")


def _iou(box1, box2):
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    xa = max(x1, x2)
    ya = max(y1, y2)
    xb = min(x1 + w1, x2 + w2)
    yb = min(y1 + h1, y2 + h2)

    inter_w = max(0, xb - xa)
    inter_h = max(0, yb - ya)
    inter_area = inter_w * inter_h

    union_area = w1 * h1 + w2 * h2 - inter_area
    return inter_area / union_area if union_area > 0 else 0


def _merge_boxes(boxes, iou_threshold=0.35):
    merged = []
    for box in boxes:
        x, y, w, h, source = box
        should_keep = True
        for existing in merged:
            ex, ey, ew, eh, _ = existing
            if _iou((x, y, w, h), (ex, ey, ew, eh)) > iou_threshold:
                should_keep = False
                break
        if should_keep:
            merged.append(box)
    return merged


class HaarFaceDetector:
    def __init__(self):
        if not OPENCV_AVAILABLE:
            raise RuntimeError("OpenCV 不可用")

        ai_cfg = getattr(settings, 'AI_MONITOR', {})
        haar_cfg = ai_cfg.get('HAAR', {})

        frontal_model = haar_cfg.get('FRONTAL_MODEL', 'haarcascade_frontalface_alt2.xml')
        profile_model = haar_cfg.get('PROFILE_MODEL', 'haarcascade_profileface.xml')

        frontal_path = cv2.data.haarcascades + frontal_model
        profile_path = cv2.data.haarcascades + profile_model

        self.frontal_cascade = cv2.CascadeClassifier(frontal_path)
        self.profile_cascade = cv2.CascadeClassifier(profile_path)

        if self.frontal_cascade.empty():
            raise RuntimeError(f"正脸模型加载失败: {frontal_path}")

        if self.profile_cascade.empty():
            logger.warning(f"⚠️ 侧脸模型加载失败: {profile_path}")
            self.profile_cascade = None

        self.pass1_cfg = haar_cfg.get('PASS1', {
            'scaleFactor': 1.1,
            'minNeighbors': 4,
            'min_ratio': 0.08,
            'min_px': 40,
        })
        self.pass2_cfg = haar_cfg.get('PASS2', {
            'scaleFactor': 1.06,
            'minNeighbors': 3,
            'min_ratio': 0.05,
            'min_px': 28,
        })
        self.profile_cfg = haar_cfg.get('PROFILE', {
            'scaleFactor': 1.1,
            'minNeighbors': 4,
            'min_ratio': 0.07,
            'min_px': 36,
        })

        self.max_image_width = ai_cfg.get('MAX_IMAGE_WIDTH', 960)
        self.enable_profile_face = ai_cfg.get('ENABLE_PROFILE_FACE', True)
        self.enable_relaxed_pass = ai_cfg.get('ENABLE_RELAXED_PASS', True)

    def _resize_if_needed(self, image):
        h, w = image.shape[:2]
        if w <= self.max_image_width:
            return image, 1.0

        scale = self.max_image_width / w
        resized = cv2.resize(image, (int(w * scale), int(h * scale)))
        return resized, scale

    def _detect_with_cfg(self, cascade, gray, cfg, source):
        h, w = gray.shape[:2]
        short_side = min(h, w)
        min_px = max(cfg.get('min_px', 40), int(short_side * cfg.get('min_ratio', 0.08)))

        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=cfg.get('scaleFactor', 1.1),
            minNeighbors=cfg.get('minNeighbors', 4),
            minSize=(min_px, min_px),
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        return [
            (int(x), int(y), int(w_box), int(h_box), source)
            for (x, y, w_box, h_box) in faces
        ]

    def detect(self, image):
        start_time = time.time()

        resized_img, resize_scale = self._resize_if_needed(image)
        gray = cv2.cvtColor(resized_img, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.equalizeHist(gray)

        all_faces = []

        # 第一轮：正脸标准检测
        all_faces.extend(
            self._detect_with_cfg(
                self.frontal_cascade,
                gray_eq,
                self.pass1_cfg,
                "frontal_pass1"
            )
        )

        # 第二轮：如果没检测到，则放宽再试
        if self.enable_relaxed_pass and len(all_faces) == 0:
            all_faces.extend(
                self._detect_with_cfg(
                    self.frontal_cascade,
                    gray_eq,
                    self.pass2_cfg,
                    "frontal_pass2"
                )
            )

        # 第三轮：侧脸检测（左侧）
        if self.enable_profile_face and self.profile_cascade is not None:
            all_faces.extend(
                self._detect_with_cfg(
                    self.profile_cascade,
                    gray_eq,
                    self.profile_cfg,
                    "profile_left"
                )
            )

            # 第四轮：侧脸检测（右侧，翻转后再修正坐标）
            flipped_gray = cv2.flip(gray_eq, 1)
            right_faces = self._detect_with_cfg(
                self.profile_cascade,
                flipped_gray,
                self.profile_cfg,
                "profile_right"
            )

            width_total = gray_eq.shape[1]
            corrected_right_faces = []
            for x, y, w_box, h_box, source in right_faces:
                corrected_x = width_total - x - w_box
                corrected_right_faces.append((corrected_x, y, w_box, h_box, source))

            all_faces.extend(corrected_right_faces)

        # 去重
        all_faces = _merge_boxes(all_faces, iou_threshold=0.35)

        # 还原到原图坐标
        if resize_scale != 1.0:
            restored_faces = []
            for x, y, w_box, h_box, source in all_faces:
                restored_faces.append((
                    int(x / resize_scale),
                    int(y / resize_scale),
                    int(w_box / resize_scale),
                    int(h_box / resize_scale),
                    source
                ))
            all_faces = restored_faces

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return {
            'success': True,
            'faces': [
                {
                    'x': x,
                    'y': y,
                    'w': w_box,
                    'h': h_box,
                    'source': source
                }
                for x, y, w_box, h_box, source in all_faces
            ],
            'count': len(all_faces),
            'detector': 'haar_alt2',
            'latency_ms': latency_ms,
            'image_shape': image.shape[:2],
        }


_detector_instance = None


def get_detector():
    global _detector_instance

    if _detector_instance is None:
        backend = getattr(settings, 'AI_MONITOR', {}).get('DEFAULT_BACKEND', 'haar')

        if backend != 'haar':
            raise NotImplementedError(f"当前仅实现 haar 检测后端，当前配置为: {backend}")

        _detector_instance = HaarFaceDetector()

    return _detector_instance


def face_backend_available():
    if not OPENCV_AVAILABLE:
        return False, "OpenCV 或 numpy 未安装"

    try:
        get_detector()
        return True, ""
    except Exception as e:
        logger.error(f"人脸检测器初始化失败: {e}")
        return False, str(e)


def detect_faces_from_base64(image_data):
    if not OPENCV_AVAILABLE:
        raise RuntimeError("OpenCV 不可用")

    if not image_data:
        raise ValueError("没有图像数据")

    if ',' in image_data:
        image_data = image_data.split(',')[1]

    img_bytes = base64.b64decode(image_data)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("图片解码失败")

    detector = get_detector()
    return detector.detect(img)