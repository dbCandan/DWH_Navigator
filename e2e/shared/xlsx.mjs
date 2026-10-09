import {inflateRawSync} from 'node:zlib';

/**
 * The text of the parts of an Excel workbook (a zip file) whose names match, read with the standard
 * library only: the central directory gives each part's local header, and a part is stored or
 * deflated.
 */
export function workbookText(buffer, pattern = /^xl\/.*\.xml$/) {
  const end = buffer.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (end < 0) throw new Error('not a zip file');
  const count = buffer.readUInt16LE(end + 10);
  let at = buffer.readUInt32LE(end + 16);
  const parts = [];
  for (let i = 0; i < count; i++) {
    const method = buffer.readUInt16LE(at + 10);
    const size = buffer.readUInt32LE(at + 20);
    const nameLength = buffer.readUInt16LE(at + 28);
    const extra = buffer.readUInt16LE(at + 30);
    const comment = buffer.readUInt16LE(at + 32);
    const local = buffer.readUInt32LE(at + 42);
    const entry = buffer.subarray(at + 46, at + 46 + nameLength).toString('utf8');
    if (pattern.test(entry)) {
      const start = local + 30 + buffer.readUInt16LE(local + 26) + buffer.readUInt16LE(local + 28);
      const data = buffer.subarray(start, start + size);
      parts.push((method === 0 ? data : inflateRawSync(data)).toString('utf8'));
    }
    at += 46 + nameLength + extra + comment;
  }
  return parts.join('\n');
}
