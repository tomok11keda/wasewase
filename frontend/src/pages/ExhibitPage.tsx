import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  createProduct,
  fetchExhibitMeta,
  type FilterTab,
} from "../features/flea/api";
import { spaLoginPath } from "../features/auth/api";

export function ExhibitPage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const [facultyChoices, setFacultyChoices] = useState<FilterTab[]>([]);
  const [campusChoices, setCampusChoices] = useState<FilterTab[]>([]);
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [campus, setCampus] = useState("");
  const [description, setDescription] = useState("");
  const [courseName, setCourseName] = useState("");
  const [professorName, setProfessorName] = useState("");
  const [faculty, setFaculty] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/flea/exhibit"), { replace: true });
      return;
    }
    void fetchExhibitMeta()
      .then((meta) => {
        setFacultyChoices(meta.faculty_choices);
        setCampusChoices(meta.campus_choices);
      })
      .catch(() => {
        setError("フォーム情報の取得に失敗しました");
      });
  }, [me?.authenticated, sessionLoading]);

  if (sessionLoading || !me?.authenticated) {
    return (
      <div className="exhibit-page" data-spa-page="フリマ">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!image) {
      setError("商品画像を1枚以上追加してください");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("name", name.trim());
      form.set("price", price.trim());
      form.set("handover_campus", campus);
      form.set("description", description);
      form.set("course_name", courseName);
      form.set("professor_name", professorName);
      form.set("faculty", faculty);
      form.set("image", image);
      const product = await createProduct(form);
      navigate(`/flea?exhibit_success=1`);
      void product;
    } catch (err) {
      setError(err instanceof Error ? err.message : "出品に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="exhibit-page" data-spa-page="フリマ">
      <div className="main-inner">
        <Link className="back-link" to="/flea">
          ← フリマへ戻る
        </Link>
        <h2 style={{ margin: "0 0 8px", fontSize: 18 }}>商品を出品</h2>
        <p className="form-lead">
          受け渡しキャンパスと商品画像は必須です。
        </p>
        {error ? (
          <p style={{ color: "#c62828", fontSize: 14 }}>{error}</p>
        ) : null}
        <form className="form-card" onSubmit={(e) => void onSubmit(e)}>
          <div className="form-group">
            <label htmlFor="exhibit-image">写真（必須）</label>
            <input
              id="exhibit-image"
              type="file"
              accept="image/*"
              required
              onChange={(e) => setImage(e.target.files?.[0] || null)}
            />
          </div>
          <div className="form-group">
            <label htmlFor="exhibit-name">商品名</label>
            <input
              id="exhibit-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：黒のトートバッグ、線形代数の教科書"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="exhibit-price">価格</label>
            <input
              id="exhibit-price"
              type="number"
              min={0}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="1000"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="exhibit-campus">受け渡しキャンパス</label>
            <select
              id="exhibit-campus"
              value={campus}
              onChange={(e) => setCampus(e.target.value)}
              required
            >
              {campusChoices.map((c) => (
                <option key={c.value || "blank"} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="exhibit-description">説明文</label>
            <textarea
              id="exhibit-description"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="状態・サイズ・購入時期・受け渡しの希望など"
            />
          </div>
          <div className="form-group">
            <label htmlFor="exhibit-course">授業名</label>
            <input
              id="exhibit-course"
              value={courseName}
              onChange={(e) => setCourseName(e.target.value)}
              placeholder="例：線形代数Ⅰ（任意）"
            />
          </div>
          <div className="form-group">
            <label htmlFor="exhibit-professor">教授名</label>
            <input
              id="exhibit-professor"
              value={professorName}
              onChange={(e) => setProfessorName(e.target.value)}
              placeholder="例：山田太郎（任意）"
            />
          </div>
          <div className="form-group">
            <label htmlFor="exhibit-faculty">対象学部</label>
            <select
              id="exhibit-faculty"
              value={faculty}
              onChange={(e) => setFaculty(e.target.value)}
            >
              {facultyChoices.map((f) => (
                <option key={f.value || "blank-f"} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
          <button className="btn-submit" type="submit" disabled={busy || !image}>
            {busy ? "出品中…" : "出品する"}
          </button>
        </form>
      </div>
    </div>
  );
}
