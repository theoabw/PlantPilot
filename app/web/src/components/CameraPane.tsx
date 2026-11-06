import { useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { errorMessage } from '../api'
import { imageBlobToJpeg, videoFrameToJpeg } from '../imaging'

type CameraPaneProps = {
  busy: boolean
  onFrame: (frame: Blob) => void
  onLoadSample: () => void
}

type CameraState = 'starting' | 'live' | 'unavailable'

export default function CameraPane({ busy, onFrame, onLoadSample }: CameraPaneProps) {
  // getUserMedia needs a secure context: localhost and https qualify, a LAN http number does not.
  const secure = typeof window === 'undefined' ? true : window.isSecureContext
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const previewUrlRef = useRef<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [cameraState, setCameraState] = useState<CameraState>('starting')
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const fileInputId = useId()

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancelled = false

    async function startCamera() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setCameraState('unavailable')
        setCameraError('This browser has no camera access. Use the photo upload below.')
        return
      }

      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 1920 },
            height: { ideal: 1080 },
            facingMode: 'environment',
          },
          audio: false,
        })

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        const video = videoRef.current
        if (!video) {
          return
        }

        video.srcObject = stream
        try {
          await video.play()
        } catch {
          // A muted autoplay stream is normally allowed. If the browser blocks
          // it, the frames still arrive once the user presses scan.
        }

        if (!cancelled) {
          setCameraState('live')
        }
      } catch (error) {
        if (cancelled) {
          return
        }
        setCameraState('unavailable')
        setCameraError(`Camera unavailable (${errorMessage(error)}). Use the photo upload below.`)
      }
    }

    void startCamera()

    return () => {
      cancelled = true
      if (stream) {
        stream.getTracks().forEach((track) => track.stop())
      }
    }
  }, [])

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current)
      }
    }
  }, [])

  function rememberPreview(blob: Blob) {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
    }
    const url = URL.createObjectURL(blob)
    previewUrlRef.current = url
    setPreview(url)
  }

  async function handleScan() {
    setCaptureError(null)
    const video = videoRef.current
    if (!video) {
      setCaptureError('The camera is not ready. Use the photo upload below.')
      return
    }

    try {
      const frame = await videoFrameToJpeg(video)
      rememberPreview(frame)
      onFrame(frame)
    } catch (error) {
      setCaptureError(errorMessage(error))
    }
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset the input so choosing the same file twice fires change again.
    event.target.value = ''
    setCaptureError(null)
    if (!file) {
      return
    }

    try {
      const frame = await imageBlobToJpeg(file)
      rememberPreview(frame)
      onFrame(frame)
    } catch (error) {
      setCaptureError(errorMessage(error))
    }
  }

  const statusText =
    cameraState === 'live' ? 'camera live' : cameraState === 'starting' ? 'starting camera' : 'no camera'

  const statusClass =
    cameraState === 'live'
      ? 'border-emerald-700 bg-emerald-100 text-emerald-900'
      : cameraState === 'starting'
        ? 'border-slate-500 bg-slate-100 text-slate-900'
        : 'border-red-700 bg-red-100 text-red-900'

  return (
    <section className="flex h-full min-h-0 flex-col gap-3 rounded-xl border-2 border-slate-300 bg-white p-4 shadow-sm">
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="text-xl font-bold tracking-tight text-slate-900">Camera</h2>
        <span className={`rounded-full border-2 px-3 py-0.5 text-base font-bold ${statusClass}`}>
          {statusText}
        </span>
      </header>

      <div className="relative min-h-[120px] flex-1 overflow-hidden rounded-lg border-2 border-slate-900 bg-slate-900">
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="h-full w-full object-contain"
        />

        {cameraState === 'unavailable' ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-900 px-6 text-center">
            <p className="text-xl font-bold text-white">Camera not available</p>
            <p className="text-base font-semibold text-slate-100">
              Use the photo upload below to scan a stored plate.
            </p>
          </div>
        ) : null}
      </div>

      {cameraError ? (
        <p className="text-base font-semibold text-red-800">{cameraError}</p>
      ) : null}

      <button
        type="button"
        onClick={() => void handleScan()}
        disabled={busy || cameraState !== 'live'}
        className="flex w-full items-center justify-center gap-3 rounded-lg border-2 border-blue-900 bg-blue-800 px-4 py-3 text-xl font-bold text-white hover:bg-blue-900 disabled:cursor-not-allowed disabled:border-slate-500 disabled:bg-slate-300 disabled:text-slate-800"
      >
        {busy ? (
          <>
            <span
              aria-hidden="true"
              className="h-6 w-6 animate-spin rounded-full border-[3px] border-white border-t-transparent"
            />
            scanning...
          </>
        ) : (
          'scan nameplate'
        )}
      </button>

      {!secure ? (
        <p className="rounded-lg border-2 border-amber-600 bg-amber-50 px-3 py-2 text-base font-semibold text-amber-900">
          This page is open on a network address, not a secure one, so the browser
          will not give it the live camera. Take a photo with the phone camera and
          upload it here. The laptop on localhost keeps the live camera.
        </p>
      ) : null}

      <div>
        <label
          htmlFor={fileInputId}
          className={`block w-full cursor-pointer rounded-lg border-2 border-slate-900 px-4 py-3 text-center text-lg font-bold hover:bg-slate-100 ${secure ? 'bg-white text-slate-900' : 'bg-blue-800 text-white hover:bg-blue-900'}`}
        >
          {secure ? 'or upload a photo' : 'take a photo, then upload it'}
        </label>
        <input
          id={fileInputId}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(event) => void handleFile(event)}
          className="sr-only"
        />
      </div>

      {captureError ? (
        <p className="text-base font-bold text-red-800">{captureError}</p>
      ) : null}

      {preview ? (
        <div className="flex items-center gap-3">
          <img
            src={preview}
            alt="the frame that was sent to the backend"
            className="h-20 w-28 shrink-0 rounded-md border-2 border-slate-400 object-cover"
          />
          <div>
            <p className="text-base font-bold text-slate-900">last frame sent</p>
            <p className="text-base font-semibold text-slate-700">JPEG, field name: frame</p>
          </div>
        </div>
      ) : null}

      {import.meta.env.DEV ? (
        <div className="flex items-center justify-between gap-3 rounded-lg border-2 border-dashed border-slate-400 bg-slate-50 px-3 py-1.5">
          <span className="text-base font-semibold text-slate-700">sample data</span>
          <button
            type="button"
            onClick={onLoadSample}
            className="rounded-md border-2 border-slate-900 bg-white px-3 py-1 text-base font-bold text-slate-900 hover:bg-slate-100"
          >
            load sample
          </button>
        </div>
      ) : null}
    </section>
  )
}
