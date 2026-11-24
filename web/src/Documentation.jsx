import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Folder,
  FolderOpen,
  FileText,
  Plus,
  Upload,
  ArrowLeft,
  ChevronRight,
  ChevronDown,
  Search,
  Trash2,
  Undo2,
  MoveRight,
  Copy,
  Pencil,
  MoreHorizontal,
  Download,
  Tags,
} from "lucide-react";
import { api, record } from "./api";
import { Dialog, Field } from "./components";
import "./documentation.css";
const tagSet = (value) =>
  new Set(
    (value || "")
      .normalize("NFKC")
      .toLocaleLowerCase()
      .split(",")
      .map((t) => t.trim().replace(/\s+/g, " "))
      .filter(Boolean),
  );
const tagMatch = (folder, lift) => {
  const required = [...tagSet(folder.documentation_tags)];
  const actual = tagSet(lift.documentation_tags);
  return required.length > 0 && required.every((t) => actual.has(t));
};
const folderMatches = (folder, lift) =>
  folder.elevator_id === lift.id || tagMatch(folder, lift);
const date = (value) =>
  value ? new Date(value).toLocaleDateString("ru-RU") : "—";
const fileSize = value => value == null ? '—' : value < 1024*1024 ? (value/1024).toLocaleString('ru-RU',{maximumFractionDigits:0})+' КБ' : (value/(1024*1024)).toLocaleString('ru-RU',{maximumFractionDigits:1})+' МБ';
const folderKey = (f) => "f" + f.id,
  docKey = (d) => "d" + d.id;
export default function Documentation({ user, data, lift = null }) {
  const readOnly = !!lift || !user.can_manage;
  const canTrash = !lift && user.can_manage_access;
  const [catalog, setCatalog] = useState({ folders: [], documents: [] }),
    [place, setPlace] = useState({}),
    [selection, setSelection] = useState([]),
    [query, setQuery] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [dialog, setDialog] = useState(null),
    [context, setContext] = useState(null),
    [expanded, setExpanded] = useState(new Set()),
    [loaded, setLoaded] = useState(false);
  const uploadRef = useRef(),
    host = useRef();
  const refresh = useCallback(async () => {
    try {
      setCatalog(
        await api("document-folders/" + (place.trash ? "?trash=1" : "")),
      );
      setLoaded(true);
    } catch (e) {
      setError(e.message);
    }
  }, [place.trash]);
  useEffect(() => {
    const abort = new AbortController();
    api("document-folders/" + (place.trash ? "?trash=1" : ""), {
      signal: abort.signal,
    })
      .then((value) => {
        setCatalog(value);
        setLoaded(true);
        setError("");
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [place.trash, user.organization_id]);
  useEffect(() => {
    if (dialog || context || busy) return;
    const id = setInterval(() => {
      if (!document.hidden) refresh();
    }, 15000);
    return () => clearInterval(id);
  }, [refresh, dialog, context, busy]);
  useEffect(() => {
    if (!context) return;
    const close = () => setContext(null);
    document.addEventListener("click", close);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("click", close);
      window.removeEventListener("resize", close);
    };
  }, [context]);
  const { folders, documents } = catalog;
  const byId = new Map(folders.map((f) => [f.id, f]));
  const active = byId.get(place.folder);
  const elevator = lift;
  const elevatorName = (e) => {
    const b = (data.buildings || []).find((b) => b.id === e.building);
    return `${b?.address || e.address || "Лифт"} · ${e.entrance_kind === "LIFT" ? "Лифт №" : "Подъезд "}${e.entrance || e.inventory_number || e.id}`;
  };
  const eligibleRoots = elevator
    ? folders.filter((f) => folderMatches(f, elevator))
    : folders;
  const allowed = new Set();
  if (lift) {
    const add = (id) => {
      if (allowed.has(id)) return;
      allowed.add(id);
      folders.filter((f) => f.parent_id === id).forEach((f) => add(f.id));
    };
    eligibleRoots.forEach((f) => add(f.id));
  }
  const visibleFolder = (f) => !lift || allowed.has(f.id);
  let listFolders = folders.filter(
    (f) =>
      visibleFolder(f) &&
      (place.trash
        ? !byId.has(f.parent_id)
        : active
          ? f.parent_id === active.id
          : !f.parent_id),
  );
  if (lift && !active)
    listFolders = eligibleRoots.filter(
      (f) =>
        !eligibleRoots.some((other) => {
          let p = byId.get(f.parent_id);
          while (p) {
            if (p.id === other.id) return true;
            p = byId.get(p.parent_id);
          }
          return false;
        }),
    );
  const legacyMatches = (d) => {
    const required = [...tagSet(d.documentation_tags)],
      actual = tagSet(lift?.documentation_tags);
    return required.length
      ? required.every((t) => actual.has(t))
      : d.manufacturer &&
          d.manufacturer.toLocaleLowerCase() ===
            (lift?.manufacturer || "").toLocaleLowerCase() &&
          (!d.model ||
            d.model.toLocaleLowerCase() ===
              (lift?.model || "").toLocaleLowerCase());
  };
  let listDocs = documents.filter((d) =>
    place.trash
      ? !byId.has(d.folder)
      : active
        ? d.folder === active.id
        : lift
          ? !allowed.has(d.folder) && legacyMatches(d)
          : !elevator && !d.folder,
  );
  if (query.trim()) {
    const matches = (text) =>
      (text || "")
        .toLocaleLowerCase()
        .includes(query.trim().toLocaleLowerCase());
    listFolders = folders.filter(
      (f) =>
        visibleFolder(f) && (matches(f.name) || matches(f.documentation_tags)),
    );
    listDocs = documents.filter(
      (d) =>
        (!lift || allowed.has(d.folder) || legacyMatches(d)) &&
        (matches(d.title) || matches(d.documentation_tags)),
    );
  }
  const rows = [
    ...listFolders.map((f) => ({
      key: folderKey(f),
      folder: f,
      name: f.name,
      tags: f.documentation_tags,
      date: f.updated_at,
    })),
    ...listDocs.map((d) => ({
      key: docKey(d),
      doc: d,
      name: d.title,
      tags: d.documentation_tags,
      date: d.updated_at,
    })),
  ];
  // Tree selections include the open folder even when it is not a row in its own contents.
  const selectedRows = [
    ...folders.map(f => ({key: folderKey(f), folder: f, name: f.name})),
    ...documents.map(d => ({key: docKey(d), doc: d, name: d.title})),
  ].filter(row => selection.includes(row.key));
  const navigate = (next) => {
    setPlace(next);
    setSelection([]);
    setQuery("");
    setContext(null);
  };
  const openFolder = (f) => {
    setExpanded((prev) => new Set([...prev, "f" + f.id]));
    navigate({ folder: f.id });
  };
  const breadcrumbs = [];
  let parent = active;
  const seen = new Set();
  while (parent && !seen.has(parent.id) && (!lift || allowed.has(parent.id))) {
    seen.add(parent.id);
    breadcrumbs.unshift(parent);
    parent = byId.get(parent.parent_id);
  }
  const selectedPayload = () => ({
    folders: selectedRows.filter((r) => r.folder).map((r) => r.folder.id),
    documents: selectedRows.filter((r) => r.doc).map((r) => r.doc.id),
  });
  const run = async (payload) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api("document-folders/", { method: "POST", body: payload });
      setDialog(null);
      setSelection([]);
      await refresh();
      if (payload.action === 'delete' && breadcrumbs.some(folder => (payload.folders || []).includes(folder.id))) navigate({});
      setNotice("Изменения сохранены");
      record("documentation", payload.action, "ok");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const chooseAction = (action) => {
    setContext(null);
    if (!selectedRows.length) return;
    if (action === "restore") run({ action, ...selectedPayload() });
    else if (action === "rename")
      setDialog(
        selectedRows[0].folder
          ? { kind: "folder", folder: selectedRows[0].folder }
          : { kind: "rename", doc: selectedRows[0].doc },
      );
    else setDialog({ kind: action });
  };
  const openDocument = (d) => {
    if (d.url) window.open(d.url, "_blank", "noopener,noreferrer");
  };
  const showContext = (event, row) => {
    event.preventDefault();
    if (!selection.includes(row.key)) setSelection([row.key]);
    setContext({
      x: Math.max(8, Math.min(event.clientX, innerWidth - 236)),
      y: Math.max(8, Math.min(event.clientY, innerHeight - 330)),
      row,
    });
  };
  const drop = async (event, target) => {
    event.preventDefault();
    if (readOnly || place.trash || busy) return;
    try {
      const payload = JSON.parse(
        event.dataTransfer.getData("application/x-liftcontrol-documents"),
      );
      if (payload.organization !== user.organization_id) return;
      await run({
        action: "move",
        folders: payload.folders,
        documents: payload.documents,
        target,
      });
    } catch {
      setError(
        "Не удалось переместить элементы. Используйте кнопку «Переместить».",
      );
    }
  };
  const dragProps = (target) => ({
    onDragOver: (e) => {
      if (
        !readOnly &&
        !place.trash &&
        e.dataTransfer.types.includes("application/x-liftcontrol-documents")
      )
        e.preventDefault();
    },
    onDrop: (e) => drop(e, target),
  });
  const treeFolder = (f, depth = 0) => {
    if (depth > 30) return null;
    const key = "f" + f.id,
      children = folders.filter((x) => x.parent_id === f.id),
      opened = expanded.has(key) || breadcrumbs.some((x) => x.id === f.id);
    return (
      <div key={key}>
        <div
          className={"doc-tree-line " + (active?.id === f.id ? "active" : "")}
          style={{ paddingInlineStart: 12 + depth * 16 }}
          {...dragProps(f.id)}
          onContextMenu={event => { if (!readOnly) showContext(event, {key:folderKey(f),folder:f,name:f.name}); }}
        >
          <button
            className="doc-expander"
            aria-label={(opened ? "Свернуть " : "Развернуть ") + f.name}
            onClick={() =>
              setExpanded((prev) => {
                const next = new Set(prev);
                next.has(key) ? next.delete(key) : next.add(key);
                return next;
              })
            }
          >
            {children.length ? (
              opened ? (
                <ChevronDown size={15} />
              ) : (
                <ChevronRight size={15} />
              )
            ) : null}
          </button>
          <button className="doc-tree-name" onClick={() => openFolder(f)}>
            <Folder size={18} />
            <span>{f.name}</span>
            {f.documentation_tags && <Tags size={12} />}
          </button>
          {!readOnly && <button className="icon-button" aria-label={'Действия папки: '+f.name}
            onClick={event => { event.stopPropagation(); showContext(event, {key:folderKey(f),folder:f,name:f.name}); }}>
            <MoreHorizontal size={17}/>
          </button>}
        </div>
        {opened && children.map((child) => treeFolder(child, depth + 1))}
      </div>
    );
  };
  const upload = async (files) => {
    if (!files.length || busy) return;
    if (!active) {
      setError("Сначала откройте или создайте папку для документов.");
      return;
    }
    setBusy(true);
    setError("");
    let count = 0;
    try {
      for (const file of files) {
        if (!file.name.toLowerCase().endsWith(".pdf"))
          throw Error("Сейчас поддерживаются документы PDF.");
        const body = new FormData();
        body.append("title", file.name.slice(0, 200));
        body.append("folder", active.id);
        body.append("file", file);
        await api("documents/", { method: "POST", body });
        count++;
      }
      setNotice(`Загружено файлов: ${count}`);
    } catch (e) {
      setError(`Загружено: ${count} из ${files.length}. ${e.message}`);
    } finally {
      await refresh();
      setBusy(false);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  };
  return (
    <section
      ref={host}
      className={"documentation " + (lift ? "doc-embedded" : "")}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          setContext(null);
          setSelection([]);
        }
        if (
          e.target.closest("input,textarea,select") ||
          readOnly ||
          place.trash
        )
          return;
        if (e.key === "F2" && selectedRows.length === 1) {
          e.preventDefault();
          chooseAction("rename");
        }
        if (e.key === "Delete" && canTrash && selectedRows.length) {
          e.preventDefault();
          chooseAction("delete");
        }
      }}
    >
      {!lift && (
        <header className="doc-heading">
          <div>
            <span className="eyebrow">ОБЩАЯ БИБЛИОТЕКА</span>
            <h1>Документация</h1>
            <p>Ваши папки и документы в одном месте</p>
          </div>
          {canTrash && (
            <button
              className={place.trash ? "primary" : ""}
              onClick={() => navigate(place.trash ? {} : { trash: true })}
            >
              <Trash2 size={17} />
              {place.trash ? "Из корзины к документам" : "Корзина"}
            </button>
          )}
        </header>
      )}
      {lift && (
        <p className="notice">
          Папки подобраны по тегам и привязке к лифту. Документы доступны для
          просмотра и скачивания.
        </p>
      )}
      <div className="doc-toolbar">
        {!readOnly && !place.trash && (
          <>
            <button onClick={() => setDialog({ kind: "folder" })}>
              <Plus size={17} />
              Новая папка
            </button>
            <button
              disabled={busy || !active}
              onClick={() => uploadRef.current.click()}
            >
              <Upload size={17} />
              Загрузить PDF
            </button>
            <input
              hidden
              ref={uploadRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              onChange={(e) => upload([...e.target.files])}
            />
            {active && canTrash && <button className="danger" disabled={busy}
              onClick={() => {setSelection([folderKey(active)]);setDialog({kind:'delete'});}}>
              <Trash2 size={17}/>Удалить папку
            </button>}
            <span className="doc-tool-divider" />
            <button
              disabled={busy || !selectedRows.length}
              className="doc-bulk-action"
              onClick={() => chooseAction("move")}
            >
              <MoveRight size={17} />
              Переместить
            </button>
            <button
              disabled={busy || !selectedRows.length}
              className="doc-bulk-action"
              onClick={() => chooseAction("copy")}
            >
              <Copy size={17} />
              Копировать
            </button>
            <button
              disabled={busy || selectedRows.length !== 1}
              className="doc-bulk-action"
              onClick={() => chooseAction("rename")}
            >
              <Pencil size={17} />
              Изменить
            </button>
            {canTrash && (
              <button
                disabled={busy || !selectedRows.length}
                className="doc-bulk-action"
              onClick={() => chooseAction("delete")}
              >
                <Trash2 size={17} />
                Удалить
              </button>
            )}
          </>
        )}
        {place.trash && canTrash && (
          <button
            disabled={busy || !selectedRows.length}
            onClick={() => chooseAction("restore")}
          >
            <Undo2 size={17} />
            Восстановить
          </button>
        )}
        <label className="doc-search">
          <Search size={18} />
          <input
            aria-label="Поиск документов и папок"
            placeholder="Поиск по имени и тегам"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelection([]);
            }}
          />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="doc-status">
          {notice}
        </p>
      )}
      <div className="doc-explorer">
        {!lift && !place.trash && (
          <aside className="doc-tree" aria-label="Дерево документации">
            <button
              className={
                "doc-tree-root " + (!active ? "active" : "")
              }
              onClick={() => navigate({})}
              {...dragProps(null)}
            >
              <FolderOpen size={20} />
              Документация
            </button>
            {folders
              .filter((f) => !f.parent_id)
              .map((f) => treeFolder(f))}

          </aside>
        )}
        <div className="doc-content">
          <nav className="doc-breadcrumb" aria-label="Путь к папке">
            <button
              aria-label="На уровень выше"
              disabled={!active}
              onClick={() =>
                navigate(
                  active?.parent_id && (!lift || allowed.has(active.parent_id))
                    ? { folder: active.parent_id }
                    : {},
                )
              }
            >
              <ArrowLeft size={17} />
            </button>
            <button onClick={() => navigate({})}>
              {place.trash ? "Корзина" : "Документация"}
            </button>
            {elevator && (
              <>
                <ChevronRight size={14} />
                <button onClick={() => navigate({})}>
                  {elevatorName(elevator)}
                </button>
              </>
            )}
            {breadcrumbs.map((f) => (
              <React.Fragment key={f.id}>
                <ChevronRight size={14} />
                <button onClick={() => openFolder(f)}>{f.name}</button>
              </React.Fragment>
            ))}
          </nav>
          {active?.documentation_tags && (
            <div className="doc-tags">
              <Tags size={15} />
              {active.documentation_tags.split(",").map((t) => (
                <span key={t}>{t.trim()}</span>
              ))}
            </div>
          )}
          <div
            className="doc-list"
            role="table"
            aria-label="Файлы и папки"
            aria-busy={busy}
          >
            <div className="doc-row doc-list-head" role="row">
              <span role="columnheader">
                {!readOnly && (
                  <input
                    type="checkbox"
                    aria-label="Выбрать все элементы"
                    checked={
                      rows.length > 0 && rows.every(row => selection.includes(row.key))
                    }
                    onChange={(e) =>
                      setSelection(
                        e.target.checked ? rows.map((r) => r.key) : [],
                      )
                    }
                  />
                )}
              </span>
              <span role="columnheader">Имя</span>
              <span role="columnheader">Изменён</span>
              <span role="columnheader">Размер</span>
              <span />
            </div>
            {rows.map((row) => (
              <div
                role="row"
                key={row.key}
                className={
                  "doc-row " + (selection.includes(row.key) ? "selected" : "")
                }
                onContextMenu={(e) => !readOnly && showContext(e, row)}
                draggable={!readOnly && !place.trash && !busy}
                onDragStart={(e) => {
                  const keys = selection.includes(row.key)
                    ? selection
                    : [row.key];
                  setSelection(keys);
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData(
                    "application/x-liftcontrol-documents",
                    JSON.stringify({
                      organization: user.organization_id,
                      folders: keys
                        .filter((k) => k[0] === "f")
                        .map((k) => Number(k.slice(1))),
                      documents: keys
                        .filter((k) => k[0] === "d")
                        .map((k) => Number(k.slice(1))),
                    }),
                  );
                }}
                {...(row.folder ? dragProps(row.folder.id) : {})}
              >
                <span role="cell">
                  {!readOnly && (
                    <input
                      type="checkbox"
                      aria-label={"Выбрать " + row.name}
                      disabled={busy}
                      checked={selection.includes(row.key)}
                      onChange={(e) =>
                        setSelection((prev) =>
                          e.target.checked
                            ? [...prev, row.key]
                            : prev.filter((k) => k !== row.key),
                        )
                      }
                    />
                  )}
                </span>
                <button
                  role="cell"
                  className="doc-filename"
                  disabled={place.trash}
                  onClick={() =>
                    row.folder ? openFolder(row.folder) : openDocument(row.doc)
                  }
                >
                  {row.folder ? (
                    <Folder className="doc-folder-icon" size={24} />
                  ) : (
                    <FileText className="doc-pdf-icon" size={24} />
                  )}
                  <span>
                    <b>{row.name}</b>
                    {row.tags && <small>{row.tags}</small>}
                  </span>
                </button>
                <span role="cell" className="doc-date">
                  {date(row.date)}
                </span>
                <span role="cell" className="doc-type">
                  {row.folder ? "—" : fileSize(row.doc.size)}
                </span>
                <span role="cell">
                  {!readOnly ? (
                    <button
                      className="icon-button"
                      aria-label={"Действия: " + row.name}
                      onClick={(e) => {
                        e.stopPropagation();
                        showContext(e, row);
                      }}
                    >
                      <MoreHorizontal size={20} />
                    </button>
                  ) : (
                    row.doc && (
                      <a
                        className="icon-button"
                        href={row.doc.url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={"Скачать " + row.name}
                      >
                        <Download size={18} />
                      </a>
                    )
                  )}
                </span>
              </div>
            ))}
            {!rows.length && (
              <div className="doc-empty">
                <FolderOpen size={44} />
                <h3>
                  {!loaded
                    ? "Загрузка…"
                    : query
                      ? "Ничего не найдено"
                      : place.trash
                        ? "Корзина пуста"
                        : "Здесь пока пусто"}
                </h3>
                <p>
                  {!readOnly && !query && !place.trash
                    ? "Создайте папку, задайте теги и загрузите документы PDF."
                    : "Подходящих документов пока нет."}
                </p>
                {!readOnly && !place.trash && !query && (
                  <button onClick={() => setDialog({ kind: "folder" })}>
                    <Plus size={16} />
                    Создать папку
                  </button>
                )}
              </div>
            )}
          </div>
          <footer className="doc-footer">
            Элементов: {rows.length}
            {selectedRows.length > 0 && ` · Выбрано: ${selectedRows.length}`}
            {busy && " · Сохранение…"}
          </footer>
        </div>
      </div>
      {context && !readOnly && (
        <div
          className="doc-context"
          role="menu"
          style={{ left: context.x, top: context.y }}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            if (e.key === "Escape") setContext(null);
          }}
        >
          {!place.trash && (
            <>
              <button
                role="menuitem"
                onClick={() => {
                  context.row.folder
                    ? openFolder(context.row.folder)
                    : openDocument(context.row.doc);
                  setContext(null);
                }}
              >
                <FolderOpen size={17} />
                Открыть
              </button>
              {context.row.doc && (
                <a
                  role="menuitem"
                  href={context.row.doc.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => setContext(null)}
                >
                  <Download size={17} />
                  Скачать PDF
                </a>
              )}
              <button
                role="menuitem"
                disabled={selectedRows.length !== 1}
                onClick={() => chooseAction("rename")}
              >
                <Pencil size={17} />
                Переименовать / теги
              </button>
              <button role="menuitem" onClick={() => chooseAction("move")}>
                <MoveRight size={17} />
                Переместить в…
              </button>
              <button role="menuitem" onClick={() => chooseAction("copy")}>
                <Copy size={17} />
                Копировать в…
              </button>
              {canTrash && (
                <button
                  role="menuitem"
                  className="danger"
                  onClick={() => chooseAction("delete")}
                >
                  <Trash2 size={17} />
                  Удалить
                </button>
              )}
            </>
          )}
          {place.trash && (
            <button role="menuitem" onClick={() => chooseAction("restore")}>
              <Undo2 size={17} />
              Восстановить
            </button>
          )}
        </div>
      )}
      {dialog && (
        <ExplorerDialog
          key={dialog.kind + (dialog.folder?.id || dialog.doc?.id || "")}
          dialog={dialog}
          folders={folders}
          place={place}
          active={active}
          busy={busy}
          error={error}
          selected={selectedRows}
          onClose={() => !busy && setDialog(null)}
          onRun={run}
          onRename={async (title) => {
            setBusy(true);
            setError("");
            try {
              await api("documents/" + dialog.doc.id + "/", {
                method: "PATCH",
                body: { title, expected_updated_at: dialog.doc.updated_at },
              });
              setDialog(null);
              await refresh();
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        />
      )}
    </section>
  );
}
function ExplorerDialog({
  dialog,
  folders,
  place,
  active,
  busy,
  error,
  selected,
  onClose,
  onRun,
  onRename,
}) {
  const folder = dialog.folder;
  const [name, setName] = useState(folder?.name || dialog.doc?.title || ""),
    [tags, setTags] = useState(folder?.documentation_tags || ""),
    [target, setTarget] = useState(folder?.parent_id ? 'f'+folder.parent_id : folder ? '' : active ? 'f'+active.id : ''),
    [reason, setReason] = useState("");
  const kind = dialog.kind,
    isFolder = kind === "folder",
    isRename = kind === "rename",
    isDelete = kind === "delete";
  const blocked = new Set(
    selected.filter((r) => r.folder).map((r) => r.folder.id),
  );
  if (folder) blocked.add(folder.id);
  let changed = true;
  while (changed) {
    changed = false;
    for (const f of folders)
      if (blocked.has(f.parent_id) && !blocked.has(f.id)) {
        blocked.add(f.id);
        changed = true;
      }
  }
  const path = (f) => {
    const parts = [f.name],
      seen = new Set([f.id]);
    let parent = folders.find((x) => x.id === f.parent_id);
    while (
      parent &&
      !seen.has(parent.id)
    ) {
      seen.add(parent.id);
      parts.unshift(parent.name);
      parent = folders.find((x) => x.id === parent.parent_id);
    }
    return parts.join(" / ");
  };
  const title = isFolder
    ? folder
      ? "Свойства папки"
      : "Новая папка"
    : isRename
      ? "Переименовать документ"
      : isDelete
        ? "Переместить в корзину"
        : kind === "copy"
          ? "Копировать в папку"
          : "Переместить в папку";
  const payload = () => ({
    target: target[0] === "f" ? Number(target.slice(1)) : null,
  });
  const submit = (e) => {
    e.preventDefault();
    if (isRename) {
      onRename(name);
      return;
    }
    if (isFolder) {
      const p = payload();
      onRun({
        action: folder ? "edit" : "create",
        id: folder?.id,
        name,
        documentation_tags: tags,
        parent_id: p.target,
        ...(folder ? {elevator_id: folder.elevator_id} : {}),
      });
      return;
    }
    onRun({
      action: kind,
      folders: selected.filter((r) => r.folder).map((r) => r.folder.id),
      documents: selected.filter((r) => r.doc).map((r) => r.doc.id),
      reason,
      ...payload(),
    });
  };
  return (
    <Dialog title={title} onClose={onClose}>
      <form className="doc-form" onSubmit={submit}>
        {(isFolder || isRename) && (
          <Field label="Название">
            <input
              autoFocus
              required
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
        )}
        {isFolder && (
          <>
            <Field label="Теги папки через запятую">
              <input
                maxLength={640}
                placeholder="мэл, monarch, nice3000"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </Field>
            <p className="muted">
              Папка со всем содержимым появится в карточке лифта, если у лифта
              указаны все эти теги. Например: «мэл, monarch». Папки без тегов
              остаются в общей библиотеке.
            </p>
          </>
        )}
        {(isFolder || (!isRename && !isDelete)) && (
          <Field label={isFolder ? "Расположение" : "Куда"}>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Документация — общие папки</option>
              {folders
                .filter((f) => !blocked.has(f.id))
                .map((f) => (
                  <option key={"f" + f.id} value={"f" + f.id}>
                    {path(f)}
                  </option>
                ))}
            </select>
          </Field>
        )}
        {isDelete && (
          <>
            <p>
              Выбрано элементов: {selected.length}. Вложенные папки и документы
              также попадут в корзину. Их можно восстановить.
            </p>
            <Field label="Причина удаления">
              <textarea
                required
                minLength={5}
                maxLength={1000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
          </>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" disabled={busy} onClick={onClose}>
            Отмена
          </button>
          <button
            className={isDelete ? "danger" : "primary"}
            disabled={busy}
            type="submit"
          >
            {busy ? "Сохранение…" : isDelete ? "В корзину" : "Сохранить"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
