import { useId, useState } from "react";
import ReactMarkdown from "react-markdown";

const SOURCE_PREFIX = "#rag-source-";
const CITATION = /\[(S\d+(?:,\s*p{1,2}\.\s*\d+(?:\s*[-–,]\s*\d+)*)?(?:\s*[,;]\s*S\d+(?:,\s*p{1,2}\.\s*\d+(?:\s*[-–,]\s*\d+)*)?)*)\]/g;

// Transform Markdown text nodes, leaving code, links and images intact.
function remarkCitations({ sources }) {
  const ids = new Set(sources.map((source) => source.source_id));
  return (tree) => {
    function visit(node) {
      if (!node.children || ["link", "image", "code", "inlineCode", "html"].includes(node.type)) return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== "text") {
          visit(child);
          return [child];
        }
        const pieces = [];
        let offset = 0;
        for (const match of child.value.matchAll(CITATION)) {
          const labels = match[1].match(/S\d+/g);
          if (!labels.every((label) => ids.has(label))) continue;
          pieces.push({ type: "text", value: child.value.slice(offset, match.index) });
          const entries = match[1].split(/\s*[,;]\s*(?=S\d+)/);
          pieces.push({ type: "text", value: "[" });
          entries.forEach((entry, index) => {
            if (index) pieces.push({ type: "text", value: ", " });
            pieces.push({
              type: "link", url: `${SOURCE_PREFIX}${labels[index]}`,
              children: [{ type: "text", value: entry }],
            });
          });
          pieces.push({ type: "text", value: "]" });
          offset = match.index + match[0].length;
        }
        pieces.push({ type: "text", value: child.value.slice(offset) });
        return pieces;
      });
    }
    visit(tree);
  };
}

export default function SourceMessage({ message }) {
  const sources = Array.isArray(message.sources) ? message.sources : [];
  const [activeId, setActiveId] = useState(null);
  const panelId = useId();
  const active = sources.find((source) => source.source_id === activeId);

  return (
    <>
      <div className="markdown-content">
        <ReactMarkdown
          remarkPlugins={[[remarkCitations, { sources }]]}
          components={{
            a: ({ href, children }) => {
              const sourceId = href?.startsWith(SOURCE_PREFIX) ? href.slice(SOURCE_PREFIX.length) : null;
              if (!sources.some((source) => source.source_id === sourceId)) {
                return <a href={href}>{children}</a>;
              }
              return (
                <button
                  type="button" className="citation-button"
                  aria-label={`查看来源 ${sourceId}`}
                  aria-expanded={activeId === sourceId} aria-controls={panelId}
                  onClick={() => setActiveId((current) => current === sourceId ? null : sourceId)}
                >{children}</button>
              );
            },
          }}
        >{message.content}</ReactMarkdown>
      </div>
      {message.content && sources.length === 0 && (
        <p className="source-card-note">本条回答暂无可展开的来源。</p>
      )}
      {active && (
        <section className="source-card" id={panelId} aria-label={`来源 ${active.source_id}`}>
          <div className="source-card-heading">
            <strong>{active.source_id} · {active.filename || "论文来源"}</strong>
            <button type="button" onClick={() => setActiveId(null)} aria-label="关闭来源卡片">×</button>
          </div>
          <p className="source-card-meta">
            PDF 页码：{active.page_nums?.length ? active.page_nums.join("、") : "未知"}
            {active.section_path?.length > 0 && ` · ${active.section_path.join(" > ")}`}
          </p>
          <div className="source-card-text">{active.text}</div>
          <p className="source-card-note">生成回答时使用的检索片段；可能含章节前缀、关联图注或图片描述，请结合论文核对。</p>
        </section>
      )}
    </>
  );
}
