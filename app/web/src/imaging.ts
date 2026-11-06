// Frame capture helpers. The API expects a JPEG in the multipart field "frame",
// so everything taken from the camera or the file picker is encoded to JPEG.

function canvasToJpeg(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob)
        } else {
          reject(new Error('this browser could not encode the frame as JPEG'))
        }
      },
      'image/jpeg',
      quality,
    )
  })
}

export async function videoFrameToJpeg(
  video: HTMLVideoElement,
  quality = 0.92,
): Promise<Blob> {
  const width = video.videoWidth
  const height = video.videoHeight

  if (!width || !height) {
    throw new Error('the camera has not produced a frame yet')
  }

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height

  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('this browser cannot draw the camera frame')
  }

  context.drawImage(video, 0, 0, width, height)
  return canvasToJpeg(canvas, quality)
}

// Re-encode an uploaded photo to JPEG so the backend always receives the
// declared content type. If the browser cannot decode the file, send it as is.
export async function imageBlobToJpeg(blob: Blob, quality = 0.92): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(blob)
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height

    const context = canvas.getContext('2d')
    if (!context) {
      bitmap.close()
      return blob
    }

    context.drawImage(bitmap, 0, 0)
    bitmap.close()
    return await canvasToJpeg(canvas, quality)
  } catch {
    return blob
  }
}
