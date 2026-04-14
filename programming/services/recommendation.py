from collections import Counter

from django.urls import reverse

from programming.models import CodeProblem, CodeSubmission, ProblemFavorite, UserProblemStatus
from programming.services.problem_zones import ZONE_CONFIGS, build_zone_buckets, get_problem_zone


ZONE_NAME_MAP = {zone['slug']: zone['name'] for zone in ZONE_CONFIGS}
ZONE_META_MAP = {zone['slug']: zone for zone in ZONE_CONFIGS}

ROUTE_META = {
    'priority': {'label': '优先补强', 'color': '#f97316'},
    'steady': {'label': '继续稳固', 'color': '#8b5cf6'},
    'advance': {'label': '可以进阶', 'color': '#22c55e'},
}


def _difficulty_rank(value):
    mapping = {
        'easy': 1,
        '简单': 1,
        'medium': 2,
        '中等': 2,
        'hard': 3,
        '困难': 3,
    }
    return mapping.get(value, 2)


def _stage_rank(value):
    mapping = {
        '入门': 1,
        '提升': 2,
        '进阶': 3,
        '冲刺': 4,
    }
    return mapping.get(value, 2)


def _status_label(status):
    return {
        'not_started': '未开始',
        'tried': '已尝试',
        'passed': '已通过',
        'needs_work': '待攻克',
    }.get(status, '未开始')


def _split_csv(value):
    return [item.strip() for item in str(value or '').replace('，', ',').split(',') if item.strip()]


def _safe_percent(numerator, denominator):
    return round((numerator / denominator) * 100, 2) if denominator else 0


def _clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def _build_problem_card(problem, *, user_status=None, reason='', bucket='', score=0):
    zone = get_problem_zone(problem)
    status_value = getattr(user_status, 'status', 'not_started') if user_status else 'not_started'
    return {
        'id': problem.id,
        'title': problem.title,
        'difficulty': getattr(problem, 'get_difficulty_display', lambda: problem.difficulty)(),
        'stage': getattr(problem, 'get_recommend_stage_display', lambda: problem.recommend_stage)(),
        'category': getattr(problem, 'get_category_display', lambda: problem.category)(),
        'estimated_minutes': getattr(problem, 'estimated_minutes', 15) or 15,
        'status': _status_label(status_value),
        'reason': reason,
        'bucket': bucket,
        'score': round(score, 2),
        'zone_slug': zone['slug'],
        'zone_name': zone['name'],
        'detail_url': reverse('programming:problem_detail', kwargs={'pk': problem.id}),
        'zone_url': reverse('programming:problem_zone_detail', kwargs={'zone_slug': zone['slug']}),
        'tags': _split_csv(getattr(problem, 'tags', ''))[:4],
        'knowledge_points': _split_csv(getattr(problem, 'knowledge_points', ''))[:4],
    }


def _get_status_map(user):
    return {
        item.problem_id: item
        for item in UserProblemStatus.objects.filter(user=user).select_related('problem')
    }


def _zone_route(zone_stat, weak_zone_slugs, strong_zone_slugs):
    if zone_stat['slug'] in weak_zone_slugs or zone_stat['retrying'] > 0:
        return 'priority'
    if zone_stat['slug'] in strong_zone_slugs and zone_stat['attempted'] > 0:
        return 'advance'
    return 'steady'


def _pick_zone_keywords(zone_problems, limit=3):
    counter = Counter()
    for problem in zone_problems:
        for item in _split_csv(getattr(problem, 'knowledge_points', '')):
            counter[item] += 3
        for item in _split_csv(getattr(problem, 'tags', '')):
            counter[item] += 2
        category = getattr(problem, 'get_category_display', lambda: getattr(problem, 'category', ''))()
        if category:
            counter[category] += 1

    words = []
    for name, count in counter.most_common():
        if name not in words:
            words.append(name)
        if len(words) >= limit:
            break
    return words


def _build_zone_stats(all_problems, status_map):
    zone_buckets = build_zone_buckets(all_problems)
    zone_stats = []

    for zone in ZONE_CONFIGS:
        zone_problems = zone_buckets.get(zone['slug'], [])
        zone_problem_ids = {problem.id for problem in zone_problems}
        statuses = [status_map[problem_id] for problem_id in zone_problem_ids if problem_id in status_map]

        attempted = sum(1 for item in statuses if getattr(item, 'attempt_count', 0) > 0)
        passed = sum(1 for item in statuses if getattr(item, 'status', '') == 'passed')
        retrying = sum(1 for item in statuses if getattr(item, 'status', '') == 'needs_work')
        wrong_count = sum(getattr(item, 'wrong_count', 0) for item in statuses)

        pass_rate = _safe_percent(passed, attempted)
        coverage_rate = _safe_percent(attempted, len(zone_problems))
        stability_score = _clamp(round(pass_rate * 0.55 + coverage_rate * 0.2 + max(0, 30 - wrong_count) * 0.6))
        heat = _clamp(round(25 + retrying * 18 + wrong_count * 0.9 + (100 - pass_rate) * 0.28))
        keywords = _pick_zone_keywords(zone_problems, limit=3)

        zone_stats.append({
            'slug': zone['slug'],
            'name': zone['name'],
            'icon': zone.get('icon', 'bi bi-grid-1x2'),
            'accent': zone.get('accent', '#0ea5e9'),
            'subtitle': zone.get('subtitle', ''),
            'problem_count': len(zone_problems),
            'attempted': attempted,
            'passed': passed,
            'retrying': retrying,
            'wrong_count': wrong_count,
            'pass_rate': pass_rate,
            'coverage_rate': coverage_rate,
            'stability_score': stability_score,
            'heat': heat,
            'keywords': keywords,
            'problem_titles': [problem.title for problem in zone_problems[:4]],
            'zone_url': reverse('programming:problem_zone_detail', kwargs={'zone_slug': zone['slug']}),
            'problems': zone_problems,
        })

    return zone_stats


def _pick_weak_zones(zone_stats):
    candidates = [item for item in zone_stats if item['problem_count'] > 0]
    candidates.sort(
        key=lambda item: (
            -item['retrying'],
            -item['wrong_count'],
            item['pass_rate'],
            item['coverage_rate'],
            item['name'],
        )
    )
    return candidates


def _pick_strong_zones(zone_stats):
    candidates = [item for item in zone_stats if item['attempted'] > 0]
    candidates.sort(
        key=lambda item: (
            -item['pass_rate'],
            -item['passed'],
            item['wrong_count'],
            -item['coverage_rate'],
            item['name'],
        )
    )
    return candidates


def _build_summary(all_problems, status_map, favorites_count, submissions_count):
    attempted_count = sum(1 for item in status_map.values() if getattr(item, 'attempt_count', 0) > 0)
    passed_count = sum(1 for item in status_map.values() if getattr(item, 'status', '') == 'passed')
    needs_work_count = sum(1 for item in status_map.values() if getattr(item, 'status', '') == 'needs_work')
    pass_rate = _safe_percent(passed_count, attempted_count)

    return {
        'total_problem_count': len(all_problems),
        'attempted_count': attempted_count,
        'passed_count': passed_count,
        'needs_work_count': needs_work_count,
        'favorite_count': favorites_count,
        'submissions_count': submissions_count,
        'pass_rate': pass_rate,
    }


def _score_problem(problem, status_obj, *, bucket, weak_zone_slugs, strong_zone_slugs):
    zone = get_problem_zone(problem)
    score = 0.0
    score += getattr(problem, 'recommendation_weight', 1) * 10
    score += max(0, 4 - _difficulty_rank(getattr(problem, 'difficulty', 'medium'))) * 2
    score += max(0, 5 - _stage_rank(getattr(problem, 'recommend_stage', '提升')))

    if status_obj:
        score += getattr(status_obj, 'attempt_count', 0) * 1.5
        score += getattr(status_obj, 'wrong_count', 0) * 3
        if getattr(status_obj, 'status', '') == 'needs_work':
            score += 18
        elif getattr(status_obj, 'status', '') == 'tried':
            score += 8
        elif getattr(status_obj, 'status', '') == 'passed':
            score -= 20
    else:
        score += 4

    if zone['slug'] in weak_zone_slugs:
        score += 8
    if zone['slug'] in strong_zone_slugs:
        score += 4

    if bucket == 'weakness' and getattr(problem, 'is_for_weakness_fix', True):
        score += 10
    if bucket == 'improvement' and getattr(problem, 'is_for_improvement', True):
        score += 8
    if bucket == 'challenge' and getattr(problem, 'is_for_challenge', False):
        score += 12
    return score


def _build_reason(problem, status_obj, *, bucket, weak_zone_names, strong_zone_names):
    zone = get_problem_zone(problem)
    attempts = getattr(status_obj, 'attempt_count', 0) if status_obj else 0
    wrong_count = getattr(status_obj, 'wrong_count', 0) if status_obj else 0

    if bucket == 'weakness':
        if wrong_count > 0:
            return f'你在“{zone["name"]}”方向最近累计出错 {wrong_count} 次，先用这题补住薄弱点更稳。'
        if zone['name'] in weak_zone_names:
            return f'“{zone["name"]}”是你当前较薄弱的分区，建议优先补强。'
        return '这道题更适合作为当前薄弱项的回补训练。'

    if bucket == 'improvement':
        if attempts > 0:
            return '你已经接触过同方向题目，可以用这道题继续巩固和提纯思路。'
        return '这个方向目前适合稳步推进，用来补足训练连续性。'

    if bucket == 'challenge':
        if zone['name'] in strong_zone_names:
            return f'你在“{zone["name"]}”方向表现不错，可以尝试更高一级训练。'
        return '这道题更适合作为进阶拓展，帮助你拉开层次。'

    return '系统根据你的近期表现为你推荐了这道题。'


def _select_candidates(all_problems, status_map, *, bucket, weak_zone_slugs, strong_zone_slugs, limit):
    selected = []

    for problem in all_problems:
        status_obj = status_map.get(problem.id)
        zone = get_problem_zone(problem)
        zone_slug = zone['slug']
        status_value = getattr(status_obj, 'status', 'not_started') if status_obj else 'not_started'

        if bucket == 'weakness':
            if zone_slug not in weak_zone_slugs and status_value != 'needs_work':
                continue
            if status_value == 'passed':
                continue
        elif bucket == 'improvement':
            if status_value == 'passed':
                continue
            if zone_slug in weak_zone_slugs and status_value == 'needs_work':
                continue
            if _stage_rank(getattr(problem, 'recommend_stage', '提升')) > 3:
                continue
        elif bucket == 'challenge':
            if status_value == 'passed':
                continue
            if zone_slug not in strong_zone_slugs and _difficulty_rank(getattr(problem, 'difficulty', 'medium')) < 2:
                continue
            if not getattr(problem, 'is_for_challenge', False) and _difficulty_rank(getattr(problem, 'difficulty', 'medium')) < 2:
                continue
        else:
            continue

        score = _score_problem(
            problem,
            status_obj,
            bucket=bucket,
            weak_zone_slugs=weak_zone_slugs,
            strong_zone_slugs=strong_zone_slugs,
        )
        selected.append((score, problem, status_obj))

    selected.sort(key=lambda item: (-item[0], _difficulty_rank(getattr(item[1], 'difficulty', 'medium')), item[1].id))

    weak_zone_names = {ZONE_NAME_MAP[slug] for slug in weak_zone_slugs if slug in ZONE_NAME_MAP}
    strong_zone_names = {ZONE_NAME_MAP[slug] for slug in strong_zone_slugs if slug in ZONE_NAME_MAP}

    result = []
    for score, problem, status_obj in selected[:limit]:
        result.append(
            _build_problem_card(
                problem,
                user_status=status_obj,
                reason=_build_reason(
                    problem,
                    status_obj,
                    bucket=bucket,
                    weak_zone_names=weak_zone_names,
                    strong_zone_names=strong_zone_names,
                ),
                bucket=bucket,
                score=score,
            )
        )
    return result


def _merge_today_cards(*groups, limit=6):
    seen = set()
    cards = []
    for group in groups:
        for card in group:
            if card['id'] in seen:
                continue
            seen.add(card['id'])
            cards.append(card)
            if len(cards) >= limit:
                return cards
    return cards


def _build_focus_zones(weak_zones, strong_zones):
    focus_zones = []
    strong_slugs = {item['slug'] for item in strong_zones[:2]}

    for item in weak_zones[:3]:
        route = _zone_route(item, {zone['slug'] for zone in weak_zones[:2]}, strong_slugs)
        if route == 'priority':
            action_label = '优先补强'
        elif route == 'advance':
            action_label = '可以进阶'
        else:
            action_label = '继续稳固'

        focus_zones.append({
            **item,
            'route': route,
            'action_label': action_label,
            'reason': f'待攻克 {item["retrying"]} 题，累计错误 {item["wrong_count"]} 次，通过率 {item["pass_rate"]}%。',
        })
    return focus_zones


def _build_learning_path(weakest_zone, steady_zone, strongest_zone, today_cards):
    steps = []

    if weakest_zone:
        steps.append({
            'title': f'先补 {weakest_zone["name"]}',
            'subtitle': '优先把最容易卡住你的方向稳住',
            'detail': f'当前待攻克 {weakest_zone["retrying"]} 题，累计错误 {weakest_zone["wrong_count"]} 次，建议先做 1~2 题回补。',
            'route': 'priority',
            'target_url': weakest_zone['zone_url'],
        })

    if steady_zone:
        steps.append({
            'title': f'再稳 {steady_zone["name"]}',
            'subtitle': '把已接触的方向连成连续训练',
            'detail': f'这个方向已尝试 {steady_zone["attempted"]} 题，通过率 {steady_zone["pass_rate"]}%，适合作为第二步巩固。',
            'route': 'steady',
            'target_url': steady_zone['zone_url'],
        })

    if strongest_zone:
        steps.append({
            'title': f'最后冲一题 {strongest_zone["name"]}',
            'subtitle': '把较强方向往上推一格',
            'detail': f'你在这个方向通过率 {strongest_zone["pass_rate"]}%，可以用一题中等题做小幅进阶。',
            'route': 'advance',
            'target_url': strongest_zone['zone_url'],
        })

    if not steps and today_cards:
        first = today_cards[0]
        steps.append({
            'title': f'先做 {first["title"]}',
            'subtitle': '先从推荐题起步',
            'detail': first['reason'],
            'route': 'priority',
            'target_url': first['detail_url'],
        })

    return steps[:3]


def _build_personalized_tips(summary, weakest_zone, strongest_zone, focus_zones):
    tips = []

    if summary['attempted_count'] == 0:
        return [
            '你当前还没有形成足够的做题轨迹，先从入门区连续做 2~3 题，图谱会很快变准。',
            '建议优先做 easy 题，把提交—纠错—再提交的节奏先跑起来。',
            '先不要急着铺太多方向，先把一个分区练顺更有效。',
        ]

    if weakest_zone:
        tips.append(
            f'最近最该补的是“{weakest_zone["name"]}”，不是因为题多，而是这个方向的错误和待攻克更集中。'
        )

    if strongest_zone:
        tips.append(
            f'“{strongest_zone["name"]}”已经开始形成强项，不用停留太久，可以保留少量训练后逐步进阶。'
        )

    if summary['needs_work_count'] > 0:
        tips.append(
            f'你当前共有 {summary["needs_work_count"]} 道待攻克题，建议每天先消化 1 道旧错题，再开新题。'
        )
    else:
        tips.append('当前没有明显堆积的待攻克题，可以把训练重点放在连贯推进上。')

    if focus_zones:
        zone_names = '、'.join(item['name'] for item in focus_zones[:2])
        tips.append(f'这一阶段优先盯住 {zone_names} 两个方向，不要同时开太多分区。')

    return tips[:4]


def _build_graph_insight(summary, weakest_zone, strongest_zone, focus_zones):
    if weakest_zone:
        headline = f'当前最需要优先补强的是 {weakest_zone["name"]}'
        description = (
            f'这个方向当前待攻克 {weakest_zone["retrying"]} 题、累计错误 {weakest_zone["wrong_count"]} 次，'
            f'是你最近最容易反复卡住的位置。'
        )
    else:
        headline = '当前还没有明显薄弱方向'
        description = '你的做题数据还不多，建议先从一个分区连续练几题，让画像逐步稳定。'

    secondary = focus_zones[1]['name'] if len(focus_zones) > 1 else '暂无第二重点'
    strong_name = strongest_zone['name'] if strongest_zone else '暂未形成'

    return {
        'headline': headline,
        'description': description,
        'primary_focus': weakest_zone['name'] if weakest_zone else '继续积累数据',
        'secondary_focus': secondary,
        'strong_direction': strong_name,
        'pass_rate': summary['pass_rate'],
        'needs_work_count': summary['needs_work_count'],
    }


def _build_knowledge_graph(zone_stats, weakest_zone, strongest_zone):
    weak_zone_slugs = {weakest_zone['slug']} if weakest_zone else set()
    strong_zone_slugs = {strongest_zone['slug']} if strongest_zone else set()

    nodes = [
        {
            'id': 'root',
            'name': '我的学习画像',
            'category': 0,
            'symbolSize': 68,
            'value': {
                'type': 'summary',
                'title': '当前学习画像',
                'desc': '中心节点表示当前整体做题状态，向外展开到训练方向、分区与知识点。',
            },
            'draggable': True,
        }
    ]
    links = []

    route_ids = ['priority', 'steady', 'advance']
    for idx, route_key in enumerate(route_ids, start=1):
        meta = ROUTE_META[route_key]
        nodes.append({
            'id': route_key,
            'name': meta['label'],
            'category': idx,
            'symbolSize': 42,
            'value': {
                'type': 'route',
                'title': meta['label'],
                'desc': '这是系统给你的训练方向分层。',
            },
            'draggable': True,
        })
        links.append({'source': 'root', 'target': route_key, 'lineStyle': {'width': 2.2, 'opacity': 0.55}})

    sorted_zone_stats = sorted(zone_stats, key=lambda item: (-item['heat'], item['name']))
    displayed_zone_stats = sorted_zone_stats[:5]

    for item in displayed_zone_stats:
        route_key = _zone_route(item, weak_zone_slugs, strong_zone_slugs)
        zone_node_id = f'zone-{item["slug"]}'
        nodes.append({
            'id': zone_node_id,
            'name': item['name'],
            'category': route_ids.index(route_key) + 1,
            'symbolSize': max(34, min(54, 28 + item['problem_count'] * 3 + item['retrying'] * 4)),
            'value': {
                'type': 'zone',
                'title': item['name'],
                'attempted': item['attempted'],
                'passed': item['passed'],
                'retrying': item['retrying'],
                'wrong_count': item['wrong_count'],
                'pass_rate': item['pass_rate'],
                'heat': item['heat'],
                'keywords': item['keywords'],
                'subtitle': item['subtitle'],
            },
            'draggable': True,
        })
        links.append({
            'source': route_key,
            'target': zone_node_id,
            'lineStyle': {'width': 2.8, 'opacity': 0.6},
        })

        for index, keyword in enumerate(item['keywords'][:3]):
            knowledge_node_id = f'{zone_node_id}-kw-{index}'
            nodes.append({
                'id': knowledge_node_id,
                'name': keyword,
                'category': 4,
                'symbolSize': 22 + max(0, 6 - index * 2),
                'value': {
                    'type': 'knowledge',
                    'title': keyword,
                    'desc': f'这是 {item["name"]} 当前更值得关注的知识点/标签。',
                    'zone_name': item['name'],
                    'heat': item['heat'],
                },
                'draggable': True,
            })
            links.append({
                'source': zone_node_id,
                'target': knowledge_node_id,
                'lineStyle': {'width': 1.8, 'opacity': 0.42},
            })

    categories = [
        {'name': '学习画像'},
        {'name': ROUTE_META['priority']['label']},
        {'name': ROUTE_META['steady']['label']},
        {'name': ROUTE_META['advance']['label']},
        {'name': '知识点'},
    ]

    return {
        'nodes': nodes,
        'links': links,
        'categories': categories,
        'legend': [
            {'name': '优先补强', 'color': ROUTE_META['priority']['color']},
            {'name': '继续稳固', 'color': ROUTE_META['steady']['color']},
            {'name': '可以进阶', 'color': ROUTE_META['advance']['color']},
            {'name': '知识点', 'color': '#38bdf8'},
        ],
    }


def build_recommendation_dashboard(user, limit_each=4):
    all_problems = list(CodeProblem.objects.all().order_by('id'))
    status_map = _get_status_map(user)
    favorites_count = ProblemFavorite.objects.filter(user=user).count()
    submissions_count = CodeSubmission.objects.filter(user=user).count()

    zone_stats = _build_zone_stats(all_problems, status_map)
    weak_zones = _pick_weak_zones(zone_stats)
    strong_zones = _pick_strong_zones(zone_stats)

    weak_zone_slugs = [item['slug'] for item in weak_zones[:2]]
    strong_zone_slugs = [item['slug'] for item in strong_zones[:2]]

    weakness_cards = _select_candidates(
        all_problems,
        status_map,
        bucket='weakness',
        weak_zone_slugs=weak_zone_slugs,
        strong_zone_slugs=strong_zone_slugs,
        limit=limit_each,
    )
    improvement_cards = _select_candidates(
        all_problems,
        status_map,
        bucket='improvement',
        weak_zone_slugs=weak_zone_slugs,
        strong_zone_slugs=strong_zone_slugs,
        limit=limit_each,
    )
    challenge_cards = _select_candidates(
        all_problems,
        status_map,
        bucket='challenge',
        weak_zone_slugs=weak_zone_slugs,
        strong_zone_slugs=strong_zone_slugs,
        limit=limit_each,
    )
    today_cards = _merge_today_cards(weakness_cards[:3], improvement_cards[:2], challenge_cards[:2], limit=6)

    strongest_zone = strong_zones[0] if strong_zones else None
    weakest_zone = weak_zones[0] if weak_zones else None

    focus_zones = _build_focus_zones(weak_zones, strong_zones)
    steady_zone = next(
        (
            item for item in zone_stats
            if _zone_route(item, set(weak_zone_slugs), set(strong_zone_slugs)) == 'steady' and item['problem_count'] > 0
        ),
        None,
    )
    summary = _build_summary(all_problems, status_map, favorites_count, submissions_count)

    return {
        'summary': summary,
        'focus_zones': focus_zones,
        'today_recommendations': today_cards,
        'weakness_recommendations': weakness_cards,
        'improvement_recommendations': improvement_cards,
        'challenge_recommendations': challenge_cards,
        'strongest_zone': strongest_zone,
        'weakest_zone': weakest_zone,
        'knowledge_graph': _build_knowledge_graph(zone_stats, weakest_zone, strongest_zone),
        'graph_insight': _build_graph_insight(summary, weakest_zone, strongest_zone, focus_zones),
        'learning_path': _build_learning_path(weakest_zone, steady_zone, strongest_zone, today_cards),
        'personalized_tips': _build_personalized_tips(summary, weakest_zone, strongest_zone, focus_zones),
        'priority_snapshot': sorted(zone_stats, key=lambda item: (-item['heat'], item['name']))[:3],
        'has_recommendations': bool(today_cards or weakness_cards or improvement_cards or challenge_cards),
    }