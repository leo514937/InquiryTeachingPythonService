function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(text: string): string {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

export function renderMarkdown(source: string): string {
  const text = (source || "").replace(/\r\n/g, "\n");
  if (!text.trim()) {
    return "";
  }

  const lines = text.split("\n");
  const blocks: string[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let codeLines: string[] = [];
  let inCode = false;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const html = renderInline(escapeHtml(paragraph.join(" ")));
    blocks.push(`<p>${html}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listType || !listItems.length) return;
    blocks.push(`<${listType}>${listItems.join("")}</${listType}>`);
    listItems = [];
    listType = null;
  };

  const flushCode = () => {
    if (!codeLines.length) return;
    blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeLines = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      blocks.push(`<h${level}>${renderInline(escapeHtml(headingMatch[2]))}</h${level}>`);
      continue;
    }

    const unorderedMatch = trimmed.match(/^[-*+]\s+(.+)$/);
    if (unorderedMatch) {
      flushParagraph();
      if (listType === "ol") {
        flushList();
      }
      listType = "ul";
      listItems.push(`<li>${renderInline(escapeHtml(unorderedMatch[1]))}</li>`);
      continue;
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType === "ul") {
        flushList();
      }
      listType = "ol";
      listItems.push(`<li>${renderInline(escapeHtml(orderedMatch[1]))}</li>`);
      continue;
    }

    if (listType) {
      flushList();
    }

    paragraph.push(line);
  }

  if (inCode) {
    flushCode();
  }
  flushParagraph();
  flushList();

  return blocks.join("");
}

function inlineMarkdownFromNode(node: ChildNode): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return (node.textContent || "").replace(/\n/g, " ");
  }

  const element = node as HTMLElement;
  const children = Array.from(element.childNodes).map((child) => inlineMarkdownFromNode(child)).join("");

  switch (element.tagName) {
    case "STRONG":
    case "B":
      return `**${children}**`;
    case "EM":
    case "I":
      return `*${children}*`;
    case "CODE":
      return `\`${children}\``;
    case "BR":
      return "\n";
    default:
      return children;
  }
}

export function htmlToMarkdown(html: string): string {
  if (!html.trim()) {
    return "";
  }

  const doc = new DOMParser().parseFromString(`<div id="root">${html}</div>`, "text/html");
  const root = doc.getElementById("root");
  if (!root) {
    return html.trim();
  }

  const blocks: string[] = [];

  for (const node of Array.from(root.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = (node.textContent || "").trim();
      if (text) {
        blocks.push(text);
      }
      continue;
    }

    const element = node as HTMLElement;
    const inlineText = () => inlineMarkdownFromNode(element).trim();

    switch (element.tagName) {
      case "H1":
      case "H2":
      case "H3":
      case "H4":
      case "H5":
      case "H6": {
        const level = Number(element.tagName.slice(1));
        blocks.push(`${"#".repeat(level)} ${inlineText()}`);
        break;
      }
      case "P":
        blocks.push(inlineText());
        break;
      case "UL":
      case "OL": {
        const items = Array.from(element.children).map((li, index) => {
          const content = inlineMarkdownFromNode(li).trim();
          if (element.tagName === "OL") {
            return `${index + 1}. ${content}`;
          }
          return `- ${content}`;
        });
        blocks.push(items.join("\n"));
        break;
      }
      case "PRE": {
        const code = element.textContent || "";
        blocks.push("```");
        blocks.push(code.replace(/\n$/, ""));
        blocks.push("```");
        break;
      }
      case "DIV": {
        const text = inlineText();
        if (text) {
          blocks.push(text);
        }
        break;
      }
      default: {
        const text = inlineText();
        if (text) {
          blocks.push(text);
        }
      }
    }
  }

  return blocks.join("\n\n").trim();
}
