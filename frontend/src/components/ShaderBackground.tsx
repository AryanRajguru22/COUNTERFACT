// The Stitch "glowing wave ribbons" background (ANIMATION_11), ported to a component.
// Kept low-contrast behind translucent panels, paused when the tab is hidden, and static for reduced motion.
import { useEffect, useRef } from "react";
import { useReducedMotion } from "../hooks/useBrowser";

const VERTEX = `attribute vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;

const FRAGMENT = `precision highp float;
uniform float u_time;
uniform vec2 u_resolution;
uniform vec2 u_mouse;

vec3 hash3(vec2 p) {
    vec3 q = vec3(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)), dot(p, vec2(419.2, 371.9)));
    return fract(sin(q) * 43758.5453);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(dot(hash3(i + vec2(0.0, 0.0)).xy, f - vec2(0.0, 0.0)),
                   dot(hash3(i + vec2(1.0, 0.0)).xy, f - vec2(1.0, 0.0)), u.x),
               mix(dot(hash3(i + vec2(0.0, 1.0)).xy, f - vec2(0.0, 1.0)),
                   dot(hash3(i + vec2(1.0, 1.0)).xy, f - vec2(1.0, 1.0)), u.x), u.y);
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution.xy;
    vec2 p = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / min(u_resolution.x, u_resolution.y);
    vec2 m = (u_mouse - 0.5 * u_resolution.xy) / min(u_resolution.x, u_resolution.y);
    p += (m - p) * 0.03;

    vec3 col = vec3(0.035, 0.045, 0.06);
    float t = u_time * 0.4;

    float wave1 = sin(p.x * 3.5 + t + noise(p * 2.0 + t * 0.2) * 2.5) * 0.22 - 0.15;
    float glow1 = 0.015 / (abs(p.y - wave1) + 0.02);
    float wave2 = sin(p.x * 4.8 - t * 0.8 + 1.2) * 0.18 - 0.12;
    float glow2 = 0.012 / (abs(p.y - wave2) + 0.025);
    float wave3 = sin(p.x * 2.2 + t * 0.6 + 2.8) * 0.28 - 0.22;
    float glow3 = 0.018 / (abs(p.y - wave3) + 0.03);

    vec3 cyanColor = vec3(0.02, 0.71, 0.83);
    vec3 amberColor = vec3(1.0, 0.42, 0.08);
    vec3 violetGlow = vec3(0.35, 0.12, 0.65);

    // smoothstep needs edge0 < edge1 (reversed edges are undefined in GLSL), so each falloff is written as 1 - smoothstep.
    float flare = 1.0 - smoothstep(0.0, 1.2, length(p - vec2(0.1, -0.15)));
    vec2 grid = fract(p * 24.0) - 0.5;
    float dots = (1.0 - smoothstep(0.02, 0.18, length(grid))) * (noise(p * 8.0 + t) * 0.5 + 0.5);

    col += cyanColor * glow1 * 1.4;
    col += amberColor * glow2 * 1.8 * flare;
    col += violetGlow * glow3 * 0.9;
    col += amberColor * dots * flare * 0.45;
    col += cyanColor * dots * (1.0 - flare) * 0.25;
    col = mix(vec3(0.035, 0.045, 0.06), col, 0.32); // keep the ribbons a faint accent behind the panels
    col *= 1.0 - smoothstep(0.4, 1.5, length(p));

    // Opaque and clamped: the ribbons stay a faint accent behind the translucent panels.
    gl_FragColor = vec4(min(col, vec3(0.45)), 1.0);
}`;

function compile(gl: WebGLRenderingContext, type: number, source: string): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
}

export default function ShaderBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    // No loseContext() on cleanup: StrictMode re-runs this effect on the same canvas, and a lost context cannot be reused.
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl");
    if (!gl) return; // no WebGL: the page background colour shows through
    const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
    if (!vertex || !fragment) return;
    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    const uTime = gl.getUniformLocation(program, "u_time");
    const uResolution = gl.getUniformLocation(program, "u_resolution");
    const uMouse = gl.getUniformLocation(program, "u_mouse");

    // Half resolution is plenty for a soft background and keeps the GPU cost low.
    const scale = 0.5;
    const mouse = { x: 0, y: 0 };
    let lastTime = 2000;
    const draw = (now: number) => {
      lastTime = now;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform1f(uTime, now * 0.001);
      gl.uniform2f(uResolution, canvas.width, canvas.height);
      gl.uniform2f(uMouse, mouse.x, mouse.y);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
    const resize = () => {
      canvas.width = Math.max(1, Math.floor(canvas.clientWidth * scale));
      canvas.height = Math.max(1, Math.floor(canvas.clientHeight * scale));
      draw(lastTime); // resizing clears the buffer; repaint so a paused or reduced-motion canvas is never blank
    };
    mouse.x = canvas.clientWidth * scale * 0.5;
    mouse.y = canvas.clientHeight * scale * 0.5;
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    const onMove = (event: MouseEvent) => {
      mouse.x = (event.clientX / window.innerWidth) * canvas.width;
      mouse.y = (1 - event.clientY / window.innerHeight) * canvas.height;
    };
    window.addEventListener("mousemove", onMove);

    let frame = 0;
    let running = true;
    const tick = (now: number) => {
      draw(now);
      canvas.style.opacity = "0.55"; // first real frame: the tab is visible and compositing, so fade the ribbons in
      if (running && !reduced) frame = requestAnimationFrame(tick);
    };
    if (reduced) canvas.style.opacity = "0.55"; // one still frame
    else frame = requestAnimationFrame(tick);

    const onVisibility = () => {
      cancelAnimationFrame(frame);
      running = !document.hidden;
      if (running && !reduced) frame = requestAnimationFrame(tick);
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reduced]);

  return <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 h-full w-full opacity-0 transition-opacity duration-1000" />;
}
