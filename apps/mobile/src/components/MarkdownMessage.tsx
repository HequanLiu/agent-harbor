import { memo, type ReactNode } from "react";
import { Platform, Text, View, type ImageStyle, type TextStyle } from "react-native";
import { Renderer, useMarkdown, type MarkedStyles } from "react-native-marked";
import { colors } from "./ui";

class MessageRenderer extends Renderer {
  linkImage(href: string, imageUrl: string, alt?: string, style?: ImageStyle, title?: string) {
    if (!/^https?:\/\//i.test(href) && !/^mailto:/i.test(href)) {
      return this.image(imageUrl, alt, style, title);
    }
    return super.linkImage(href, imageUrl, alt, style, title);
  }

  link(children: string | ReactNode[], href: string, style?: TextStyle, title?: string) {
    if (!/^https?:\/\//i.test(href) && !/^mailto:/i.test(href)) {
      return <Text key={this.getKey()} selectable>{children}</Text>;
    }
    return super.link(children, href, style, title);
  }
}

const markdownStyles: MarkedStyles = {
  text: { color: colors.ink, fontSize: 15, lineHeight: 25 },
  paragraph: { paddingVertical: 4 },
  h1: { color: colors.ink, fontSize: 24, lineHeight: 32 },
  h2: { color: colors.ink, fontSize: 22, lineHeight: 30 },
  h3: { color: colors.ink, fontSize: 20, lineHeight: 28 },
  h4: { color: colors.ink, fontSize: 18, lineHeight: 26 },
  h5: { color: colors.ink, fontSize: 16, lineHeight: 25 },
  h6: { color: colors.muted, fontSize: 15, lineHeight: 25 },
  link: { color: colors.teal, fontStyle: "normal", textDecorationLine: "underline" },
  blockquote: { borderLeftColor: colors.teal, borderLeftWidth: 3, paddingLeft: 12, marginVertical: 8 },
  codespan: { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", backgroundColor: colors.line, color: colors.ink },
  code: { backgroundColor: colors.pale, padding: 12, borderRadius: 8 },
  codeText: { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", fontSize: 13, lineHeight: 21, color: colors.ink },
  list: { paddingVertical: 4 },
  li: { color: colors.ink, fontSize: 15, lineHeight: 25 },
  hr: { backgroundColor: colors.line, marginVertical: 12 },
  table: { borderColor: colors.line, borderWidth: 1 },
  tableRow: { borderColor: colors.line },
  tableCell: { padding: 8, borderColor: colors.line },
};

export const MarkdownMessage = memo(function MarkdownMessage({ text }: { text: string }) {
  // A renderer per parse keeps generated element keys stable as streamed text grows.
  const content = useMarkdown(text, {
    renderer: new MessageRenderer({ selectable: true }),
    styles: markdownStyles,
    colorScheme: "light",
    selectable: true,
  });
  return <View style={{ minWidth: 0, maxWidth: "100%" }}>{content}</View>;
});
