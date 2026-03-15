from django.conf import settings


def analyze_monitor_result(image_shape, faces):
    """
    根据检测结果分析当前监测状态
    """
    h, w = image_shape[:2]
    rules = getattr(settings, 'AI_MONITOR', {}).get('STATUS_RULES', {})

    face_too_small_ratio = rules.get('FACE_TOO_SMALL_RATIO', 0.03)
    multi_face_threshold = rules.get('MULTI_FACE_THRESHOLD', 2)

    result = {
        'status': 'normal',
        'warnings': [],
        'main_face': None,
    }

    count = len(faces)

    if count == 0:
        result['status'] = 'no_face'
        result['warnings'].append('未检测到人脸')
        return result

    if count >= multi_face_threshold:
        result['status'] = 'multiple_faces'
        result['warnings'].append(f'检测到 {count} 张人脸')
        return result

    # 默认取面积最大的人脸作为主脸
    main_face = max(faces, key=lambda f: f['w'] * f['h'])
    result['main_face'] = main_face

    face_area_ratio = (main_face['w'] * main_face['h']) / (w * h) if w * h > 0 else 0

    if face_area_ratio < face_too_small_ratio:
        result['status'] = 'face_too_small'
        result['warnings'].append('人脸过小，可能离镜头太远')

    source = main_face.get('source', '')
    if 'profile' in source:
        if result['status'] == 'normal':
            result['status'] = 'side_face'
        result['warnings'].append('检测到侧脸')

    # 可选：判断人脸是否明显偏离中间区域
    face_center_x = main_face['x'] + main_face['w'] / 2
    face_center_y = main_face['y'] + main_face['h'] / 2

    if face_center_x < w * 0.2 or face_center_x > w * 0.8:
        result['warnings'].append('人脸偏离画面中心')

    if face_center_y < h * 0.15 or face_center_y > h * 0.85:
        result['warnings'].append('人脸位置偏高或偏低')

    return result


def build_monitor_message(status, count, warnings=None):
    warnings = warnings or []

    base_messages = {
        'normal': f'检测到 {count} 张人脸',
        'no_face': '未检测到人脸',
        'multiple_faces': f'检测到 {count} 张人脸，存在多人',
        'face_too_small': '检测到人脸，但人脸较小',
        'side_face': '检测到侧脸',
    }

    message = base_messages.get(status, f'检测到 {count} 张人脸')

    if warnings:
        message += '（' + '；'.join(warnings) + '）'

    return message