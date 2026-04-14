from collections import Counter

ZONE_CONFIGS = [
    {
        "slug": "starter",
        "name": "入门基础区",
        "icon": "bi-stars",
        "accent": "starter",
        "description": "适合刚开始练习编程的同学，先建立做题信心和基本输入输出、逻辑处理能力。",
        "subtitle": "从最基础的题型开始，先把手感练起来",
        "category_aliases": [
            "基础", "入门", "基础语法", "数学", "模拟", "basic", "intro", "math", "simulation",
        ],
        "knowledge_keywords": [
            "基础", "入门", "语法", "数学", "模拟", "输入输出", "逻辑",
        ],
        "tag_keywords": [
            "新手", "基础", "练手", "入门",
        ],
    },
    {
        "slug": "array-string",
        "name": "数组字符串区",
        "icon": "bi-grid-3x3-gap-fill",
        "accent": "array-string",
        "description": "围绕数组、字符串和常见数据处理题展开，是最常见、最适合刷题打基础的一大区。",
        "subtitle": "高频基础题最多，适合建立刷题手感",
        "category_aliases": [
            "数组", "字符串", "双指针", "前缀和",
            "array", "string", "two pointers", "prefix sum",
        ],
        "knowledge_keywords": [
            "数组", "字符串", "双指针", "前缀和", "滑动窗口", "遍历",
        ],
        "tag_keywords": [
            "数组", "字符串", "双指针", "滑动窗口",
        ],
    },
    {
        "slug": "data-structure",
        "name": "结构专项区",
        "icon": "bi-diagram-3-fill",
        "accent": "data-structure",
        "description": "集中练习哈希、栈、队列、链表等经典数据结构，理解结构选型与题目解法的关系。",
        "subtitle": "理解常见数据结构的使用场景",
        "category_aliases": [
            "哈希", "栈", "队列", "链表",
            "hash", "hashmap", "map", "set", "stack", "queue", "linkedlist", "linked list",
        ],
        "knowledge_keywords": [
            "哈希", "栈", "队列", "链表", "字典", "集合",
        ],
        "tag_keywords": [
            "哈希", "栈", "队列", "链表",
        ],
    },
    {
        "slug": "search-strategy",
        "name": "搜索构造区",
        "icon": "bi-compass-fill",
        "accent": "search-strategy",
        "description": "主要面向二分、贪心、递归、DFS、BFS、回溯等思维型题目，训练找规律与构造答案能力。",
        "subtitle": "从“会做题”走向“会找思路”",
        "category_aliases": [
            "二分", "贪心", "回溯", "递归", "搜索", "dfs", "bfs",
            "binary search", "greedy", "backtracking", "recursion", "search",
        ],
        "knowledge_keywords": [
            "二分", "贪心", "回溯", "递归", "dfs", "bfs", "搜索", "剪枝",
        ],
        "tag_keywords": [
            "二分", "贪心", "回溯", "递归", "搜索",
        ],
    },
    {
        "slug": "advanced",
        "name": "综合进阶区",
        "icon": "bi-trophy-fill",
        "accent": "advanced",
        "description": "收纳动态规划、树、图以及多知识点混合题，适合作为综合训练与提升分区。",
        "subtitle": "更综合、更偏进阶的训练区",
        "category_aliases": [
            "动态规划", "树", "图", "并查集", "拓扑",
            "dp", "tree", "graph", "union find", "topology",
        ],
        "knowledge_keywords": [
            "动态规划", "树", "二叉树", "图", "并查集", "拓扑", "最短路",
        ],
        "tag_keywords": [
            "动态规划", "树", "图", "进阶",
        ],
    },
]


def _normalize_text(value):
    return str(value or "").strip().lower()


def split_csv_field(field_value):
    if not field_value:
        return []
    return [item.strip() for item in str(field_value).split(",") if item.strip()]


def _get_display_value(problem, field_name):
    method = getattr(problem, f"get_{field_name}_display", None)
    if callable(method):
        try:
            return method()
        except Exception:
            return getattr(problem, field_name, "")
    return getattr(problem, field_name, "")


def get_zone_by_slug(zone_slug):
    for zone in ZONE_CONFIGS:
        if zone["slug"] == zone_slug:
            return zone
    return None


def _calc_zone_score(problem, zone):
    score = 0

    category_raw = _normalize_text(getattr(problem, "category", ""))
    category_label = _normalize_text(_get_display_value(problem, "category"))
    title = _normalize_text(getattr(problem, "title", ""))
    description = _normalize_text(getattr(problem, "description", ""))

    knowledge_points = {_normalize_text(item) for item in split_csv_field(getattr(problem, "knowledge_points", ""))}
    tags = {_normalize_text(item) for item in split_csv_field(getattr(problem, "tags", ""))}

    aliases = {_normalize_text(item) for item in zone.get("category_aliases", [])}
    knowledge_keywords = {_normalize_text(item) for item in zone.get("knowledge_keywords", [])}
    tag_keywords = {_normalize_text(item) for item in zone.get("tag_keywords", [])}

    if category_raw in aliases:
        score += 10
    if category_label in aliases:
        score += 10

    for keyword in knowledge_keywords:
        if keyword in knowledge_points:
            score += 3
        if keyword and keyword in title:
            score += 2
        if keyword and keyword in description:
            score += 1

    for keyword in tag_keywords:
        if keyword in tags:
            score += 2

    return score


def get_problem_zone(problem):
    best_zone = None
    best_score = -1

    for zone in ZONE_CONFIGS:
        score = _calc_zone_score(problem, zone)
        if score > best_score:
            best_zone = zone
            best_score = score

    if best_zone is not None and best_score > 0:
        return best_zone

    category_raw = _normalize_text(getattr(problem, "category", ""))
    if any(word in category_raw for word in ["基础", "数学", "模拟", "basic", "math"]):
        return get_zone_by_slug("starter")

    if any(word in category_raw for word in ["数组", "字符串", "双指针", "array", "string"]):
        return get_zone_by_slug("array-string")

    return get_zone_by_slug("advanced")


def build_zone_buckets(problems):
    buckets = {zone["slug"]: [] for zone in ZONE_CONFIGS}
    for problem in problems:
        zone = get_problem_zone(problem)
        buckets[zone["slug"]].append(problem)
    return buckets


def build_hot_labels(problems, limit=6):
    counter = Counter()
    for problem in problems:
        counter.update(split_csv_field(getattr(problem, "tags", "")))
        counter.update(split_csv_field(getattr(problem, "knowledge_points", "")))
    return [item for item, _ in counter.most_common(limit)]