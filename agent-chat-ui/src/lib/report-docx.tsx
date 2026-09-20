import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Document,
  ExternalHyperlink,
  HeadingLevel,
  LevelFormat,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
  type ILevelsOptions,
  type IParagraphOptions,
  type IRunOptions,
} from "docx";

// 使用和页面相同的 Markdown 解析器，避免另写一套正则解析表格、列表和强调。
export async function createReportDocx(report: {
  title: string;
  question: string;
  markdown: string;
}) {
  const html = renderToStaticMarkup(
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {report.markdown}
    </ReactMarkdown>,
  );
  const body = new DOMParser().parseFromString(html, "text/html").body;
  const numbering: { reference: string; levels: ILevelsOptions[] }[] = [];
  const inline = (
    node: Node,
    style: IRunOptions = {},
  ): (TextRun | ExternalHyperlink)[] => {
    if (node.nodeType === Node.TEXT_NODE)
      return [new TextRun({ ...style, text: node.textContent ?? "" })];
    if (!(node instanceof Element)) return [];
    if (node.tagName === "BR") return [new TextRun({ break: 1 })];
    if (node.tagName === "IMG")
      return [new TextRun(node.getAttribute("alt") ?? "")];
    const next = {
      ...style,
      ...(node.tagName === "STRONG" ? { bold: true } : {}),
      ...(node.tagName === "EM" ? { italics: true } : {}),
      ...(node.tagName === "DEL" ? { strike: true } : {}),
      ...(node.tagName === "CODE" ? { font: "Consolas" } : {}),
    };
    const runs = Array.from(node.childNodes).flatMap((child) =>
      inline(child, next),
    );
    if (node.tagName === "A") {
      const link = node.getAttribute("href") ?? "";
      if (/^(https?:|mailto:)/i.test(link))
        return [new ExternalHyperlink({ link, children: runs })];
    }
    return runs;
  };
  const blocks = (
    nodes: Node[],
    depth = 0,
    options: IParagraphOptions = {},
  ): (Paragraph | Table)[] =>
    nodes.flatMap((node): (Paragraph | Table)[] => {
      if (!(node instanceof Element))
        return node.textContent?.trim()
          ? [new Paragraph({ ...options, children: inline(node) })]
          : [];
      const tag = node.tagName;
      if (tag === "UL" || tag === "OL") {
        const reference = `list-${numbering.length}`;
        if (tag === "OL")
          numbering.push({
            reference,
            levels: [
              {
                level: Math.min(depth, 8),
                format: LevelFormat.DECIMAL,
                text: `%${Math.min(depth, 8) + 1}.`,
                start: Number(node.getAttribute("start") ?? 1),
                style: {
                  paragraph: {
                    indent: { left: 360 * (depth + 1), hanging: 260 },
                  },
                },
              },
            ],
          });
        return Array.from(node.children).flatMap((item) => {
          const children = Array.from(item.childNodes);
          const nested = children.filter(
            (child) =>
              child instanceof Element && ["UL", "OL"].includes(child.tagName),
          );
          return [
            new Paragraph({
              children: children
                .filter((child) => !nested.includes(child))
                .flatMap((child) => inline(child)),
              ...(tag === "UL"
                ? { bullet: { level: Math.min(depth, 8) } }
                : { numbering: { reference, level: Math.min(depth, 8) } }),
            }),
            ...blocks(nested, depth + 1),
          ];
        });
      }
      if (tag === "TABLE") {
        const rows = Array.from(node.querySelectorAll("tr"));
        return [
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: rows.map(
              (row, index) =>
                new TableRow({
                  tableHeader: index === 0,
                  children: Array.from(row.children).map(
                    (cell) =>
                      new TableCell({
                        shading: index === 0 ? { fill: "EAECEF" } : undefined,
                        margins: {
                          top: 100,
                          bottom: 100,
                          left: 120,
                          right: 120,
                        },
                        children: [
                          new Paragraph({
                            children: inline(cell, {
                              bold: cell.tagName === "TH",
                            }),
                          }),
                        ],
                      }),
                  ),
                }),
            ),
          }),
          new Paragraph(""),
        ];
      }
      if (tag === "BLOCKQUOTE")
        return blocks(Array.from(node.childNodes), depth, {
          indent: { left: 360 },
        });
      if (tag === "PRE")
        return [
          new Paragraph({
            children: (node.textContent ?? "")
              .trimEnd()
              .split("\n")
              .flatMap((line, i) => [
                new TextRun({
                  text: line,
                  font: "Consolas",
                  ...(i ? { break: 1 } : {}),
                }),
              ]),
          }),
        ];
      if (tag === "HR") return [new Paragraph("")];
      const heading = /^H[1-6]$/.test(tag)
        ? [
            HeadingLevel.HEADING_1,
            HeadingLevel.HEADING_2,
            HeadingLevel.HEADING_3,
            HeadingLevel.HEADING_4,
            HeadingLevel.HEADING_5,
            HeadingLevel.HEADING_6,
          ][Number(tag[1]) - 1]
        : undefined;
      return [new Paragraph({ ...options, heading, children: inline(node) })];
    });
  const children = [
    new Paragraph({ text: report.title, heading: HeadingLevel.TITLE }),
    new Paragraph({
      text: `分析问题：${report.question}`,
      spacing: { after: 240 },
    }),
    ...blocks(Array.from(body.childNodes)),
  ];
  return Packer.toBlob(
    new Document({
      title: report.title,
      creator: "经营分析助手",
      styles: {
        default: {
          document: {
            run: {
              font: { ascii: "Arial", eastAsia: "微软雅黑" },
              size: 22,
              color: "000000",
            },
            paragraph: { spacing: { after: 140, line: 300 } },
          },
          title: { run: { size: 36, bold: true, color: "000000" } },
          heading1: { run: { color: "000000", size: 30, bold: true } },
          heading2: { run: { color: "000000", size: 27, bold: true } },
          heading3: { run: { color: "000000", size: 24, bold: true } },
        },
      },
      numbering: { config: numbering },
      sections: [
        {
          properties: {
            page: {
              size: { width: 12240, height: 15840 },
              margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
            },
          },
          children,
        },
      ],
    }),
  );
}
