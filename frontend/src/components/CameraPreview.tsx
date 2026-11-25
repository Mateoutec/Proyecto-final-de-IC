import type { Camera } from "../lib/useCamera";

/**
 * Video de la cámara espejado (como un espejo) y girado según `cam.rotation`.
 * Ocupa todo su contenedor, que debe tener `position: relative`.
 */
export function CameraPreview({ cam, fit = "cover", testId }: { cam: Camera; fit?: "cover" | "contain"; testId?: string }) {
  const sideways = cam.rotation % 180 !== 0;
  return (
    <div className="absolute inset-0" style={{ containerType: "size" }}>
      <video
        ref={cam.videoRef}
        muted
        playsInline
        autoPlay
        data-testid={testId}
        className="absolute top-1/2 left-1/2 max-w-none"
        style={{
          // Girado 90° o 270°, el video llena el contenedor con el ancho y el alto intercambiados.
          width: sideways ? "100cqh" : "100cqw",
          height: sideways ? "100cqw" : "100cqh",
          objectFit: fit,
          transform: `translate(-50%, -50%) scaleX(-1) rotate(${cam.rotation}deg)`,
        }}
      />
    </div>
  );
}
