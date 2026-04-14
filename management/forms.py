import json

from django import forms

from programming.models import CodeProblem


class ProblemManageForm(forms.ModelForm):
    input_example = forms.CharField(
        required=False,
        label="输入示例（JSON）",
        widget=forms.Textarea(
            attrs={
                "rows": 7,
                "data-code-editor": "json",
                "placeholder": '{\n  "nums": [2, 7, 11, 15],\n  "target": 9\n}',
            }
        ),
        help_text='函数补全题建议填写结构化 JSON，便于前端展示参数与返回值。',
    )
    output_example = forms.CharField(
        required=False,
        label="输出示例（JSON）",
        widget=forms.Textarea(
            attrs={
                "rows": 7,
                "data-code-editor": "json",
                "placeholder": '[0, 1] 或 3',
            }
        ),
        help_text='例如：[0, 1]、true、3、{"answer": 42}',
    )
    test_cases = forms.CharField(
        required=False,
        label="测试用例（JSON 列表）",
        widget=forms.Textarea(
            attrs={
                "rows": 12,
                "data-code-editor": "json",
                "placeholder": '[\n  {"input": [[2,7,11,15], 9], "expected": [0,1]},\n  {"input": [[3,2,4], 6], "expected": [1,2]}\n]',
            }
        ),
        help_text='请使用 JSON 列表；每个测试项建议包含 input 与 expected 两个键。',
    )

    class Meta:
        model = CodeProblem
        fields = [
            "title",
            "description",
            "category",
            "difficulty",
            "recommend_stage",
            "question_type",
            "knowledge_points",
            "supported_languages",
            "estimated_minutes",
            "function_name",
            "param_names",
            "input_example",
            "output_example",
            "input_format",
            "output_format",
            "data_range",
            "sample_input",
            "sample_output",
            "test_cases",
            "solution_text",
            "video_url",
            "time_limit",
            "memory_limit",
            "source",
            "tags",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "例如：两数之和 / 最长回文子串 / 课程表"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 12,
                    "placeholder": "支持 Markdown / MathJax。建议按题意、输入约束、返回要求三部分组织。",
                }
            ),
            "knowledge_points": forms.TextInput(
                attrs={"placeholder": "多个知识点请用英文逗号分隔，如：哈希表,一次遍历,边界处理"}
            ),
            "supported_languages": forms.TextInput(attrs={"placeholder": "python,c,cpp,java"}),
            "function_name": forms.TextInput(attrs={"placeholder": "例如：twoSum / canFinish / reverseList"}),
            "param_names": forms.TextInput(attrs={"placeholder": "例如：nums,target 或 numCourses,prerequisites"}),
            "input_format": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "标准输入输出题请说明输入的每一行 / 每一列含义。",
                    "data-code-editor": "plain",
                }
            ),
            "output_format": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "标准输入输出题请说明输出格式。",
                    "data-code-editor": "plain",
                }
            ),
            "data_range": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "例如：1 <= n <= 2 * 10^5",
                    "data-code-editor": "plain",
                }
            ),
            "sample_input": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "标准输入输出题建议提供样例输入。",
                    "data-code-editor": "plain",
                }
            ),
            "sample_output": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "标准输入输出题建议提供样例输出。",
                    "data-code-editor": "plain",
                }
            ),
            "solution_text": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "可按思路分析、复杂度、关键代码、易错点来组织。",
                }
            ),
            "video_url": forms.URLInput(attrs={"placeholder": "https://example.com/video"}),
            "source": forms.TextInput(attrs={"placeholder": "题目来源，例如：CodeGaze 题库 / 洛谷 / 自编题"}),
            "tags": forms.TextInput(attrs={"placeholder": "多个标签请用英文逗号分隔，如：图,拓扑排序,入度"}),
            "estimated_minutes": forms.NumberInput(attrs={"min": 1, "max": 600}),
            "time_limit": forms.NumberInput(attrs={"min": 1, "max": 30}),
            "memory_limit": forms.NumberInput(attrs={"min": 16, "max": 2048}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._init_widget_classes()
        self._init_widget_scopes()

        if self.instance and self.instance.pk:
            self.initial["input_example"] = self._format_json(self.instance.input_example)
            self.initial["output_example"] = self._format_json(self.instance.output_example)
            self.initial["test_cases"] = self._format_json(self.instance.test_cases)

    def _init_widget_classes(self):
        for field_name, field in self.fields.items():
            widget = field.widget
            base_class = widget.attrs.get("class", "")
            if isinstance(widget, forms.Select):
                widget.attrs["class"] = f"{base_class} form-select problem-input".strip()
            else:
                widget.attrs["class"] = f"{base_class} form-control problem-input".strip()
            widget.attrs.setdefault("autocomplete", "off")

        textareas_need_code_style = {
            "input_example",
            "output_example",
            "test_cases",
            "sample_input",
            "sample_output",
            "input_format",
            "output_format",
            "data_range",
        }
        for name in textareas_need_code_style:
            self.fields[name].widget.attrs["class"] += " problem-code"

        self.fields["description"].widget.attrs["class"] += " problem-rich-text"
        self.fields["solution_text"].widget.attrs["class"] += " problem-rich-text"
        self.fields["question_type"].widget.attrs["data-role"] = "question-type-selector"

    def _init_widget_scopes(self):
        function_scope = ["function_name", "param_names", "input_example", "output_example"]
        acm_scope = ["input_format", "output_format", "sample_input", "sample_output", "data_range"]

        for name in function_scope:
            self.fields[name].widget.attrs["data-question-scope"] = "function"

        for name in acm_scope:
            self.fields[name].widget.attrs["data-question-scope"] = "acm"

        self.fields["test_cases"].widget.attrs["data-question-scope"] = "both"

    @staticmethod
    def _format_json(value):
        if value in (None, "", []):
            return ""
        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _normalize_csv(raw_value):
        if raw_value in (None, ""):
            return ""
        values = []
        seen = set()
        for item in str(raw_value).replace("，", ",").split(","):
            token = item.strip()
            if not token:
                continue
            lower = token.lower()
            if lower in seen:
                continue
            seen.add(lower)
            values.append(token)
        return ",".join(values)

    @staticmethod
    def _parse_json_value(raw_value, field_label, fallback=None, must_be_list=False):
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return [] if must_be_list else fallback

        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"{field_label} 不是合法的 JSON：{exc}")

        if must_be_list and not isinstance(parsed, list):
            raise forms.ValidationError(f"{field_label} 必须是 JSON 列表格式")
        return parsed

    def clean_input_example(self):
        return self._parse_json_value(
            self.cleaned_data.get("input_example"),
            "输入示例",
            fallback=None,
        )

    def clean_output_example(self):
        return self._parse_json_value(
            self.cleaned_data.get("output_example"),
            "输出示例",
            fallback=None,
        )

    def clean_test_cases(self):
        parsed = self._parse_json_value(
            self.cleaned_data.get("test_cases"),
            "测试用例",
            fallback=[],
            must_be_list=True,
        )

        for index, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                raise forms.ValidationError(f"测试用例第 {index} 项必须是对象格式，例如 {{\"input\": ..., \"expected\": ...}}")
            if "input" not in item:
                raise forms.ValidationError(f"测试用例第 {index} 项缺少 input 字段")
            if not any(key in item for key in ("expected", "output", "answer")):
                raise forms.ValidationError(f"测试用例第 {index} 项至少需要 expected / output / answer 其中一个字段")
        return parsed

    def clean(self):
        cleaned_data = super().clean()

        for csv_field in ["knowledge_points", "supported_languages", "tags", "param_names"]:
            cleaned_data[csv_field] = self._normalize_csv(cleaned_data.get(csv_field))

        question_type = cleaned_data.get("question_type")
        if question_type == "function":
            if not cleaned_data.get("function_name"):
                self.add_error("function_name", "函数补全题必须填写函数名。")
            if not cleaned_data.get("param_names"):
                self.add_error("param_names", "函数补全题建议填写参数名，便于前端提示与测试用例映射。")
        elif question_type == "acm":
            required_fields = {
                "input_format": "标准输入输出题建议明确输入格式。",
                "output_format": "标准输入输出题建议明确输出格式。",
                "sample_input": "标准输入输出题请至少提供一组样例输入。",
                "sample_output": "标准输入输出题请至少提供一组样例输出。",
            }
            for field_name, message in required_fields.items():
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, message)

        if not cleaned_data.get("test_cases"):
            self.add_error("test_cases", "请至少提供一组测试用例。")

        return cleaned_data
