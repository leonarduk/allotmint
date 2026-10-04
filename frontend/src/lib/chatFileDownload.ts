import type { ChatFile } from "../api";

/** The file's bytes, decoded from the base64 POST /chat sends them in. */
export const chatFileBlob = (file: ChatFile): Blob => {
  const binary = atob(file.content_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: file.media_type });
};

/**
 * Saves a file the chat assistant exported (#9039). `doc` is the document the
 * link is clicked in, so it also works from the detached chat window.
 */
export const downloadChatFile = (file: ChatFile, doc: Document = document): void => {
  const url = URL.createObjectURL(chatFileBlob(file));
  const link = doc.createElement("a");
  link.href = url;
  link.download = file.filename;
  doc.body.appendChild(link);
  link.click();
  doc.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 250);
};
