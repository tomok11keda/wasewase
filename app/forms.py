from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from .constants import FACULTY_CHOICES, HANDLE_PATTERN, WASEDA_EMAIL_ERROR, is_waseda_email
from .models import (
    Comment,
    ContentReport,
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
        label="ニックネーム（表示名）",
        max_length=80,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "例：わせ太郎",
                "autocomplete": "nickname",
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
            raise ValidationError("ニックネームを入力してください。")
        return nickname

    def clean_faculty(self):
        faculty = self.cleaned_data.get("faculty")
        if not faculty:
            raise ValidationError("学部を選択してください。")
        return faculty

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and not is_waseda_email(email):
            raise ValidationError(WASEDA_EMAIL_ERROR)
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
        user.username = ""
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


class AccountProfileForm(forms.ModelForm):
    """マイページからニックネーム・ハンドル・プロフィールを編集する。"""

    user_id = forms.CharField(
        label="ハンドル（@ID）",
        max_length=30,
        min_length=3,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "例：wase_taro",
                "autocomplete": "off",
            }
        ),
        help_text="英数字とアンダースコア（_）のみ、3〜30文字。プロフィールで @ の後ろに表示されます。",
    )

    class Meta:
        model = UserProfile
        fields = ("name", "bio", "department", "grade")
        labels = {
            "name": "ニックネーム（表示名）",
            "bio": "自己紹介",
            "department": "学部",
            "grade": "学年",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "例：わせ太郎",
                    "autocomplete": "nickname",
                }
            ),
            "bio": forms.Textarea(
                attrs={"rows": 4, "placeholder": "自己紹介や取引の希望など（任意）"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.account_user = user
        super().__init__(*args, **kwargs)
        self.fields["name"].required = False
        self.fields["name"].help_text = (
            "タイムラインなどに表示されるニックネームです。空欄の場合はハンドルが表示されます。"
        )
        if user is not None:
            self.fields["user_id"].initial = user.username

    def clean_user_id(self):
        return self.clean_username(self.cleaned_data.get("user_id"))

    def clean_username(self, value=None):
        """ハンドル変更時の形式・一意性チェック。"""
        if value is None:
            value = self.cleaned_data.get("user_id")
        return self._clean_handle(value)

    def _clean_handle(self, raw_value: str | None) -> str:
        handle = (raw_value or "").strip()
        if not handle:
            raise ValidationError("ハンドルを入力してください。")
        if not HANDLE_PATTERN.match(handle):
            raise ValidationError(
                "ハンドルは英数字とアンダースコア（_）のみ、3〜30文字で入力してください。"
            )
        qs = User.objects.filter(username__iexact=handle)
        if self.account_user:
            qs = qs.exclude(pk=self.account_user.pk)
        if qs.exists():
            raise ValidationError("このハンドルはすでに使われています。")
        return handle

    def save(self, commit=True):
        profile = super().save(commit=False)
        user_id = self.cleaned_data["user_id"]

        if commit:
            with transaction.atomic():
                profile.save()
                if self.account_user:
                    updated = User.objects.filter(pk=self.account_user.pk).update(
                        username=user_id
                    )
                    if updated != 1:
                        raise ValidationError("ユーザー情報の更新に失敗しました。")
                    self.account_user.username = user_id
            profile.refresh_from_db()
            if self.account_user:
                self.account_user.refresh_from_db()

        return profile


# 後方互換のエイリアス
ProfileForm = AccountProfileForm


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
    quoted_post_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput,
    )

    class Meta:
        model = TimelinePost
        fields = ("body", "image")
        labels = {
            "body": "つぶやき",
            "image": "写真（任意）",
        }
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "placeholder": "いま思ったこと、質問、情報共有など（280字まで）",
                    "rows": 3,
                    "maxlength": 280,
                }
            ),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

    def clean_quoted_post_id(self):
        value = self.cleaned_data.get("quoted_post_id")
        if not value:
            return None
        post = TimelinePost.objects.filter(pk=value, is_removed=False).first()
        if not post:
            raise ValidationError("引用元の投稿が見つかりません。")
        return post.pk

    def save(self, commit=True):
        post = super().save(commit=False)
        quoted_post_id = self.cleaned_data.get("quoted_post_id")
        if quoted_post_id:
            post.quoted_post_id = quoted_post_id
        if commit:
            post.save()
        return post


class CourseThreadForm(forms.ModelForm):
    class Meta:
        model = CourseThread
        fields = ("course_name", "professor_name", "faculty", "description")
        labels = {
            "course_name": "授業名（任意）",
            "professor_name": "教授名（任意）",
            "faculty": "学部（任意）",
            "description": "スレッドの説明（任意）",
        }
        widgets = {
            "course_name": forms.TextInput(
                attrs={"placeholder": "授業名（任意） 例：マクロ経済学"}
            ),
            "professor_name": forms.TextInput(
                attrs={"placeholder": "教授名（任意） 例：佐藤教授"}
            ),
            "description": forms.TextInput(
                attrs={"placeholder": "試験範囲・持ち物など（任意）"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course_name"].required = False
        self.fields["professor_name"].required = False
        self.fields["faculty"].required = False
        self.fields["description"].required = False

    def clean_course_name(self):
        value = (self.cleaned_data.get("course_name") or "").strip()
        return value or None

    def clean_professor_name(self):
        value = (self.cleaned_data.get("professor_name") or "").strip()
        return value or None


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


class CommunityThreadForm(forms.Form):
    title = forms.CharField(
        label="スレッドタイトル",
        max_length=120,
        widget=forms.TextInput(
            attrs={"placeholder": "例：2年生のおすすめ科目を教えてください"}
        ),
    )
    body = forms.CharField(
        label="本文",
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "placeholder": "相談内容や共有したいことを書いてください",
                "rows": 6,
            }
        ),
    )

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("タイトルを入力してください。")
        return title

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        if not body:
            raise forms.ValidationError("本文を入力してください。")
        return body


class CommunityThreadReplyForm(forms.Form):
    body = forms.CharField(
        label="返信",
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "placeholder": "返信を入力してください",
                "rows": 4,
            }
        ),
    )

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        if not body:
            raise forms.ValidationError("返信を入力してください。")
        return body


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


class ContentReportForm(forms.Form):
    target_type = forms.ChoiceField(
        choices=ContentReport.TargetType.choices,
        widget=forms.HiddenInput(),
    )
    target_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput())
    reason = forms.ChoiceField(
        label="通報理由",
        choices=ContentReport.Reason.choices,
        widget=forms.RadioSelect,
    )
    detail = forms.CharField(
        label="詳細（任意）",
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "状況を具体的に記入してください（任意）",
            }
        ),
    )
