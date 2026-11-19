// 浏览器录音统一转成后端要求的 16kHz 单声道 16bit WAV

export function mergeAndResample(chunkList, fromRate, toRate) {
  const total = chunkList.reduce((sum, chunk) => sum + chunk.length, 0)
  const merged = new Float32Array(total)
  let cursor = 0
  for (const chunk of chunkList) {
    merged.set(chunk, cursor)
    cursor += chunk.length
  }
  if (fromRate === toRate) return merged

  const ratio = fromRate / toRate
  const outLength = Math.floor(total / ratio)
  const out = new Float32Array(outLength)
  for (let i = 0; i < outLength; i += 1) {
    const pos = i * ratio
    const index = Math.floor(pos)
    const frac = pos - index
    const first = merged[index] || 0
    const second = merged[index + 1] ?? first
    out[i] = first + (second - first) * frac
  }
  return out
}

export function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeString = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }
  return new Blob([view], { type: 'audio/wav' })
}
