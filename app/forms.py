from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError

from .constants import FACULTY_CHOICES
from .models import (
    Comment,
    CourseThread,
    Product,
    Review,
    ThreadPost,
    TimelinePost,
    UserProfile,
)

User = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="メールアドレス",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "example@waseda.jp",
                "autofocus": True,
                "autocomplete": "email",
            }
        ),
    )

    error_messages = {
        "invalid_login": "メールアドレスまたはパスワードが正しくありません。",
        "inactive": "このアカウントは無効です。",
    }

    def clean_username(self):
        return (self.cleaned_data.get("username") or "").strip().lower()


class SignUpForm(UserCreationForm):
    nickname = forms.CharField(
        label="ユーザー名（ニックネーム）",
        max_length=150,
        required=True,
        validators=[UnicodeUsernameValidator()],
        widget=forms.TextInput(
            attrs={
                "placeholder": "例：わせ太郎",
                "autocomplete": "username",
            }
        ),
    )
    faculty = forms.ChoiceField(
        label="学部",
        choices=[("", "学部を選択してください")] + list(FACULTY_CHOICES),
        required=True,
        widget=forms.Select(attrs={"id": "id_faculty"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget = forms.EmailInput(
            attrs={
                "placeholder": "example@waseda.jp",
                "autocomplete": "email",
            }
        )
        if "username" in self.fields:
            del self.fields["username"]

    def clean_nickname(self):
        nickname = (self.cleaned_data.get("nickname") or "").strip()
        if not nickname:
            raise ValidationError("ユーザー名を入力してください。")

        email = (self.data.get("email") or "").strip().lower()
        qs = User.objects.filter(username__iexact=nickname)
        pending = User.objects.filter(email__iexact=email, is_active=False).first()
        if pending:
            qs = qs.exclude(pk=pending.pk)
        if qs.exists():
            raise ValidationError("このユーザー名はすでに使われています。")
        return nickname

    def clean_faculty(self):
        faculty = self.cleaned_data.get("faculty")
        if not faculty:
            raise ValidationError("学部を選択してください。")
        return faculty

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        existing = User.objects.filter(email__iexact=email).first()
        if existing and existing.is_active:
            raise ValidationError("このメールアドレスはすでに登録されています。")
        return email

    def validate_unique(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email, is_active=False).exists():
            return
        super().validate_unique()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        user.username = self.cleaned_data["nickname"]
        user.is_active = False
        if commit:
            user.save()
        return user


class SignupOTPVerifyForm(forms.Form):
    code = forms.CharField(
        label="認証コード",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "123456",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "maxlength": "6",
            }
        ),
    )

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code.isdigit() or len(code) != 6:
            raise ValidationError("6桁の数字を入力してください。")
        return code


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("faculty",)
        labels = {"faculty": "学部（認証バッジ）"}


class ProductExhibitForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name",
            "price",
            "description",
            "faculty",
            "course_name",
            "professor_name",
            "image",
        )
        labels = {
            "name": "商品名",
            "price": "値段",
            "description": "説明",
            "faculty": "対象の学部",
            "course_name": "授業名",
            "professor_name": "教授名",
            "image": "写真",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "例：線形代数の教科書"}),
            "price": forms.NumberInput(attrs={"placeholder": "1000", "min": 0}),
            "description": forms.Textarea(
                attrs={"placeholder": "商品の状態や取引方法など", "rows": 5}
            ),
            "course_name": forms.TextInput(
                attrs={"placeholder": "例：線形代数Ⅰ"}
            ),
            "professor_name": forms.TextInput(
                attrs={"placeholder": "例：山田太郎"}
            ),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faculty"].choices = [("", "学部を選択")] + list(FACULTY_CHOICES)
        self.fields["faculty"].required = True

    def save(self, commit=True):
        product = super().save(commit=False)
        product.category = "未分類"
        if commit:
            product.save()
        return product


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "comment")
        labels = {
            "rating": "評価",
            "comment": "コメント（任意）",
        }
        widgets = {
            "rating": forms.RadioSelect,
            "comment": forms.Textarea(
                attrs={"placeholder": "短いコメント...", "rows": 2, "maxlength": 200}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].choices = [
            (Review.Rating.BAD, "悪い ★1"),
            (Review.Rating.NORMAL, "普通 ★2"),
            (Review.Rating.GOOD, "良い ★3"),
        ]


class TimelinePostForm(forms.ModelForm):
    class Meta:
        model = TimelinePost
        fields = ("body", "course_name", "professor_name", "faculty", "image")
        labels = {
            "body": "つぶやき",
            "course_name": "授業名タグ",
            "professor_name": "教授名（任意）",
            "faculty": "対象の学部",
            "image": "写真（任意）",
        }
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "placeholder": "試験の範囲、質問、情報共有など（280字まで）",
                    "rows": 3,
                    "maxlength": 280,
                }
            ),
            "course_name": forms.TextInput(attrs={"placeholder": "例：線形代数Ⅰ"}),
            "professor_name": forms.TextInput(
                attrs={"placeholder": "教授の名前（任意） 例：山田太郎"}
            ),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faculty"].choices = [("", "自分の登録学部を使う")] + list(
            FACULTY_CHOICES
        )
        self.fields["faculty"].required = False
        self.fields["image"].required = False

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        content_type = getattr(image, "content_type", "") or ""
        if not content_type.startswith("image/"):
            raise ValidationError("画像ファイル（JPEG・PNG・GIFなど）を選択してください。")
        if image.size > 5 * 1024 * 1024:
            raise ValidationError("画像は5MB以下にしてください。")
        return image


class CourseThreadForm(forms.ModelForm):
    class Meta:
        model = CourseThread
        fields = ("course_name", "professor_name", "faculty", "description")
        labels = {
            "course_name": "授業名",
            "professor_name": "教授名",
            "faculty": "学部",
            "description": "スレッドの説明",
        }
        widgets = {
            "course_name": forms.TextInput(attrs={"placeholder": "例：マクロ経済学"}),
            "professor_name": forms.TextInput(attrs={"placeholder": "例：佐藤教授"}),
            "description": forms.TextInput(
                attrs={"placeholder": "試験範囲・持ち物など（任意）"}
            ),
        }


class ThreadPostForm(forms.ModelForm):
    class Meta:
        model = ThreadPost
        fields = ("body",)
        labels = {"body": "投稿"}
        widgets = {
            "body": forms.Textarea(
                attrs={"placeholder": "質問や情報を共有...", "rows": 4}
            ),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)
        labels = {"body": "コメント"}
        widgets = {
            "body": forms.Textarea(
                attrs={"placeholder": "コメントを入力...", "rows": 3}
            ),
        }


class TimelineCommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)
        labels = {"body": "コメント"}
        widgets = {
            "body": forms.TextInput(attrs={"placeholder": "コメントを入力..."})
        }
