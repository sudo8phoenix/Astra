import { useEffect, useRef, useState } from 'react'

function createShader(gl, type, source) {
  const shader = gl.createShader(type)
  if (!shader) {
    return null
  }
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader)
    return null
  }
  return shader
}

function createProgram(gl, vertexSource, fragmentSource) {
  const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexSource)
  const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentSource)
  if (!vertexShader || !fragmentShader) {
    return null
  }

  const program = gl.createProgram()
  if (!program) {
    return null
  }

  gl.attachShader(program, vertexShader)
  gl.attachShader(program, fragmentShader)
  gl.linkProgram(program)

  gl.deleteShader(vertexShader)
  gl.deleteShader(fragmentShader)

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program)
    return null
  }

  return program
}

const vertexShaderSource = `
  attribute vec2 a_position;
  varying vec2 v_uv;

  void main() {
    v_uv = a_position * 0.5 + 0.5;
    gl_Position = vec4(a_position, 0.0, 1.0);
  }
`

const fragmentShaderSource = `
  precision mediump float;
  varying vec2 v_uv;
  uniform vec2 u_resolution;
  uniform float u_time;
  uniform vec2 u_pointer;

  float circle(vec2 uv, vec2 center, float radius, float blur) {
    float d = length(uv - center);
    return smoothstep(radius + blur, radius - blur, d);
  }

  void main() {
    vec2 uv = v_uv;
    vec2 aspectUv = uv;
    aspectUv.x *= u_resolution.x / max(u_resolution.y, 1.0);

    float t = u_time * 0.24;
    vec2 p1 = vec2(0.22 + 0.08 * sin(t), 0.38 + 0.09 * cos(t * 1.2));
    vec2 p2 = vec2(0.74 + 0.1 * cos(t * 0.8), 0.63 + 0.08 * sin(t * 1.4));
    vec2 p3 = mix(vec2(0.5, 0.5), u_pointer, 0.18);

    float c1 = circle(uv, p1, 0.32, 0.26);
    float c2 = circle(uv, p2, 0.28, 0.24);
    float c3 = circle(uv, p3, 0.26, 0.24);

    vec3 base = vec3(0.047, 0.071, 0.114);
    vec3 amber = vec3(0.96, 0.42, 0.16);
    vec3 cyan = vec3(0.09, 0.76, 0.88);
    vec3 pearl = vec3(0.93, 0.9, 0.84);

    vec3 color = base;
    color += amber * c1 * 0.72;
    color += cyan * c2 * 0.7;
    color += pearl * c3 * 0.35;

    float grain = fract(sin(dot(uv * (u_time + 1.0), vec2(12.9898, 78.233))) * 43758.5453) * 0.035;
    color += grain;

    gl_FragColor = vec4(color, 1.0);
  }
`

export default function WebGLHeroCanvas() {
  const canvasRef = useRef(null)
  const [isSupported, setIsSupported] = useState(true)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return undefined
    }

    const gl = canvas.getContext('webgl', { antialias: true, alpha: false })
    if (!gl) {
      setIsSupported(false)
      return undefined
    }

    let animationFrameId = 0
    let disposed = false
    const pointer = { x: 0.5, y: 0.5 }

    const program = createProgram(gl, vertexShaderSource, fragmentShaderSource)
    if (!program) {
      setIsSupported(false)
      return undefined
    }

    const positionLocation = gl.getAttribLocation(program, 'a_position')
    const timeLocation = gl.getUniformLocation(program, 'u_time')
    const resolutionLocation = gl.getUniformLocation(program, 'u_resolution')
    const pointerLocation = gl.getUniformLocation(program, 'u_pointer')

    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    )

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const width = Math.max(1, Math.floor(canvas.clientWidth * dpr))
      const height = Math.max(1, Math.floor(canvas.clientHeight * dpr))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      gl.viewport(0, 0, canvas.width, canvas.height)
    }

    const updatePointer = (clientX, clientY) => {
      const rect = canvas.getBoundingClientRect()
      if (!rect.width || !rect.height) {
        return
      }
      pointer.x = (clientX - rect.left) / rect.width
      pointer.y = 1 - (clientY - rect.top) / rect.height
    }

    const onMouseMove = (event) => {
      updatePointer(event.clientX, event.clientY)
    }

    const onTouchMove = (event) => {
      const touch = event.touches[0]
      if (touch) {
        updatePointer(touch.clientX, touch.clientY)
      }
    }

    const start = performance.now()

    const render = (now) => {
      if (disposed) {
        return
      }

      resize()
      gl.useProgram(program)
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.enableVertexAttribArray(positionLocation)
      gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)

      gl.uniform1f(timeLocation, (now - start) * 0.001)
      gl.uniform2f(resolutionLocation, canvas.width, canvas.height)
      gl.uniform2f(pointerLocation, pointer.x, pointer.y)

      gl.drawArrays(gl.TRIANGLES, 0, 6)
      animationFrameId = window.requestAnimationFrame(render)
    }

    resize()
    animationFrameId = window.requestAnimationFrame(render)

    window.addEventListener('resize', resize)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('touchmove', onTouchMove, { passive: true })

    return () => {
      disposed = true
      window.cancelAnimationFrame(animationFrameId)
      window.removeEventListener('resize', resize)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('touchmove', onTouchMove)
      gl.deleteBuffer(buffer)
      gl.deleteProgram(program)
    }
  }, [])

  return (
    <div className="relative h-[360px] w-full overflow-hidden rounded-[28px] border border-white/15 bg-[#121b2c] shadow-[0_30px_90px_rgba(1,4,12,0.58)] md:h-[460px]">
      {isSupported ? (
        <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-label="Interactive visual backdrop" />
      ) : (
        <div
          className="absolute inset-0 bg-[radial-gradient(circle_at_20%_30%,rgba(247,118,66,0.4),transparent_38%),radial-gradient(circle_at_75%_65%,rgba(60,190,214,0.34),transparent_42%),linear-gradient(140deg,#1a1f31,#0f1726)]"
          aria-hidden="true"
        />
      )}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(120deg,rgba(2,6,23,0.18),rgba(2,6,23,0.46))]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-[#0a101b] to-transparent" />
    </div>
  )
}
