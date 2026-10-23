/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsgpu.cpp - the DVB subtitle pages enlarged on the GPU (see hdsgpu.h).
 * New code: nothing is taken from libMali
 * (closed) or from the Khronos headers; the GL/EGL numbers below are the values of the public API, checked one by one
 * against the Khronos headers by a probe on the PC.
 *
 * The picture is the one of blit_scaled_sharp_8 (gpixmap.cpp), in three passes (GLES 2.0, framebuffer objects):
 *  1. at the source size: palette -> premultiplied colour (texture "pm", filtered LINEAR in pass 3);
 *  2. at the source size: for every 2x2 block of source pixels (i..i+1 x j..j+1, clamped at the border like the CPU),
 *     "all four the same palette entry" -> that colour, untouched (transparent -> 0), otherwise the mark (1, 1, 1, 0).
 *     This is the fast path of the CPU: inside letters, boxes and semi-transparent areas the palette colour is kept;
 *  3. only the destination area: the block under the pixel (NEAREST at the top-left bilinear tap); a kept colour goes
 *     out as it is; otherwise "pm" filtered bilinearly by the GPU (the mix of the four source pixels weighted by
 *     distance and alpha, like the CPU), alpha steepened by the enlargement and smoothed (smoothstep), colour =
 *     premultiplied / alpha, its lightness pulled to the page's darkest or lightest visible colour.
 * Written B, G, R, A, so the bytes read with glReadPixels(GL_RGBA) are enigma2's ARGB8888 in memory.
 * Mali-450 (Utgard) has no highp in fragment shaders (mediump = fp16): the texture coordinates reach texture2D straight
 * from a varying (computed in the vertex shader, fp32); the only coordinate computed in a fragment shader is the
 * palette lookup, index / 255 moved to the texel centre (error < 0.15 texel). The probe on the PC runs the same shader
 * arithmetic rounded to fp16 on the CPU.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdint.h>
#include <dirent.h>
#include <dlfcn.h>
#include <endian.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#include <lib/base/eerror.h>
#include <lib/gdi/gpixmap.h>
#include <lib/gdi/hdsgpu.h>

namespace
{

/* ------------------------------------------------------------------ the GL / EGL interface (numbers of the API) */

typedef unsigned int GLenum;
typedef unsigned int GLuint;
typedef int GLint;
typedef int GLsizei;
typedef unsigned char GLboolean;
typedef float GLfloat;
typedef char GLchar;
typedef void *EGLDisplay;
typedef void *EGLConfig;
typedef void *EGLSurface;
typedef void *EGLContext;
typedef int32_t EGLint;
typedef unsigned int EGLBoolean;
typedef unsigned int EGLenum;

enum : GLenum
{
	GLC_NO_ERROR = 0,
	GLC_TRIANGLE_STRIP = 0x0005,
	GLC_CULL_FACE = 0x0B44,
	GLC_DEPTH_TEST = 0x0B71,
	GLC_STENCIL_TEST = 0x0B90,
	GLC_DITHER = 0x0BD0,
	GLC_BLEND = 0x0BE2,
	GLC_SCISSOR_TEST = 0x0C11,
	GLC_UNPACK_ALIGNMENT = 0x0CF5,
	GLC_PACK_ALIGNMENT = 0x0D05,
	GLC_MAX_TEXTURE_SIZE = 0x0D33,
	GLC_MAX_VIEWPORT_DIMS = 0x0D3A,
	GLC_TEXTURE_2D = 0x0DE1,
	GLC_UNSIGNED_BYTE = 0x1401,
	GLC_FLOAT = 0x1406,
	GLC_RGBA = 0x1908,
	GLC_LUMINANCE = 0x1909,
	GLC_RENDERER = 0x1F01,
	GLC_VERSION = 0x1F02,
	GLC_NEAREST = 0x2600,
	GLC_LINEAR = 0x2601,
	GLC_TEXTURE_MAG_FILTER = 0x2800,
	GLC_TEXTURE_MIN_FILTER = 0x2801,
	GLC_TEXTURE_WRAP_S = 0x2802,
	GLC_TEXTURE_WRAP_T = 0x2803,
	GLC_CLAMP_TO_EDGE = 0x812F,
	GLC_TEXTURE0 = 0x84C0,
	GLC_TEXTURE1 = 0x84C1,
	GLC_FRAGMENT_SHADER = 0x8B30,
	GLC_VERTEX_SHADER = 0x8B31,
	GLC_COMPILE_STATUS = 0x8B81,
	GLC_LINK_STATUS = 0x8B82,
	GLC_FRAMEBUFFER_COMPLETE = 0x8CD5,
	GLC_COLOR_ATTACHMENT0 = 0x8CE0,
	GLC_FRAMEBUFFER = 0x8D40
};

enum : EGLint
{
	EGLC_ALPHA_SIZE = 0x3021,
	EGLC_BLUE_SIZE = 0x3022,
	EGLC_GREEN_SIZE = 0x3023,
	EGLC_RED_SIZE = 0x3024,
	EGLC_SURFACE_TYPE = 0x3033,
	EGLC_NONE = 0x3038,
	EGLC_RENDERABLE_TYPE = 0x3040,
	EGLC_HEIGHT = 0x3056,
	EGLC_WIDTH = 0x3057,
	EGLC_CONTEXT_CLIENT_VERSION = 0x3098,
	EGLC_OPENGL_ES_API = 0x30A0,
	EGLC_PBUFFER_BIT = 0x0001,
	EGLC_OPENGL_ES2_BIT = 0x0004
};

#define HDSGPU_EGL_FUNCTIONS(F) \
	F(EGLDisplay, eglGetDisplay, (void *display_id)) \
	F(EGLBoolean, eglInitialize, (EGLDisplay dpy, EGLint *major, EGLint *minor)) \
	F(EGLBoolean, eglTerminate, (EGLDisplay dpy)) \
	F(EGLBoolean, eglChooseConfig, (EGLDisplay dpy, const EGLint *attribs, EGLConfig *configs, EGLint size, EGLint *count)) \
	F(EGLSurface, eglCreatePbufferSurface, (EGLDisplay dpy, EGLConfig config, const EGLint *attribs)) \
	F(EGLBoolean, eglDestroySurface, (EGLDisplay dpy, EGLSurface surface)) \
	F(EGLBoolean, eglBindAPI, (EGLenum api)) \
	F(EGLContext, eglCreateContext, (EGLDisplay dpy, EGLConfig config, EGLContext share, const EGLint *attribs)) \
	F(EGLBoolean, eglDestroyContext, (EGLDisplay dpy, EGLContext ctx)) \
	F(EGLBoolean, eglMakeCurrent, (EGLDisplay dpy, EGLSurface draw, EGLSurface read, EGLContext ctx)) \
	F(EGLint, eglGetError, (void)) \
	F(EGLBoolean, eglReleaseThread, (void))

#define HDSGPU_GL_FUNCTIONS(F) \
	F(void, glActiveTexture, (GLenum texture)) \
	F(void, glAttachShader, (GLuint program, GLuint shader)) \
	F(void, glBindAttribLocation, (GLuint program, GLuint index, const GLchar *name)) \
	F(void, glBindFramebuffer, (GLenum target, GLuint framebuffer)) \
	F(void, glBindTexture, (GLenum target, GLuint texture)) \
	F(GLenum, glCheckFramebufferStatus, (GLenum target)) \
	F(void, glCompileShader, (GLuint shader)) \
	F(GLuint, glCreateProgram, (void)) \
	F(GLuint, glCreateShader, (GLenum type)) \
	F(void, glDeleteShader, (GLuint shader)) \
	F(void, glDisable, (GLenum cap)) \
	F(void, glDrawArrays, (GLenum mode, GLint first, GLsizei count)) \
	F(void, glEnable, (GLenum cap)) \
	F(void, glEnableVertexAttribArray, (GLuint index)) \
	F(void, glFramebufferTexture2D, (GLenum target, GLenum attachment, GLenum textarget, GLuint texture, GLint level)) \
	F(void, glGenFramebuffers, (GLsizei n, GLuint *framebuffers)) \
	F(void, glGenTextures, (GLsizei n, GLuint *textures)) \
	F(GLenum, glGetError, (void)) \
	F(void, glGetIntegerv, (GLenum pname, GLint *data)) \
	F(void, glGetProgramInfoLog, (GLuint program, GLsizei size, GLsizei *length, GLchar *log)) \
	F(void, glGetProgramiv, (GLuint program, GLenum pname, GLint *params)) \
	F(void, glGetShaderInfoLog, (GLuint shader, GLsizei size, GLsizei *length, GLchar *log)) \
	F(void, glGetShaderiv, (GLuint shader, GLenum pname, GLint *params)) \
	F(const unsigned char *, glGetString, (GLenum name)) \
	F(GLint, glGetUniformLocation, (GLuint program, const GLchar *name)) \
	F(void, glLinkProgram, (GLuint program)) \
	F(void, glPixelStorei, (GLenum pname, GLint param)) \
	F(void, glReadPixels, (GLint x, GLint y, GLsizei width, GLsizei height, GLenum format, GLenum type, void *pixels)) \
	F(void, glScissor, (GLint x, GLint y, GLsizei width, GLsizei height)) \
	F(void, glShaderSource, (GLuint shader, GLsizei count, const GLchar *const *string, const GLint *length)) \
	F(void, glTexImage2D, (GLenum target, GLint level, GLint internalformat, GLsizei width, GLsizei height, \
		GLint border, GLenum format, GLenum type, const void *pixels)) \
	F(void, glTexParameteri, (GLenum target, GLenum pname, GLint param)) \
	F(void, glTexSubImage2D, (GLenum target, GLint level, GLint xoffset, GLint yoffset, GLsizei width, \
		GLsizei height, GLenum format, GLenum type, const void *pixels)) \
	F(void, glUniform1f, (GLint location, GLfloat v0)) \
	F(void, glUniform1i, (GLint location, GLint v0)) \
	F(void, glUniform2f, (GLint location, GLfloat v0, GLfloat v1)) \
	F(void, glUniform3f, (GLint location, GLfloat v0, GLfloat v1, GLfloat v2)) \
	F(void, glUseProgram, (GLuint program)) \
	F(void, glVertexAttribPointer, (GLuint index, GLint size, GLenum type, GLboolean normalized, GLsizei stride, \
		const void *pointer)) \
	F(void, glViewport, (GLint x, GLint y, GLsizei width, GLsizei height))

struct Api
{
#define HDSGPU_MEMBER(ret, name, args) ret (*name) args;
	HDSGPU_EGL_FUNCTIONS(HDSGPU_MEMBER)
	HDSGPU_GL_FUNCTIONS(HDSGPU_MEMBER)
#undef HDSGPU_MEMBER
};

/* ------------------------------------------------------------------ the shaders (GLSL ES 1.00) */

static const char vs_plain[] =
	"attribute vec2 a_pos;\n"
	"attribute vec2 a_tc;\n"
	"varying vec2 v_tc;\n"
	"void main() { v_tc = a_tc; gl_Position = vec4(a_pos, 0.0, 1.0); }\n";

/* pass 1: palette -> premultiplied colour */
static const char fs_premultiply[] =
	"precision mediump float;\n"
	"uniform sampler2D u_idx;\n"
	"uniform sampler2D u_pal;\n"
	"varying vec2 v_tc;\n"
	"void main() {\n"
	"  float i = texture2D(u_idx, v_tc).r;\n"
	"  vec4 c = texture2D(u_pal, vec2(i * (255.0 / 256.0) + (0.5 / 256.0), 0.5));\n"
	"  gl_FragColor = vec4(c.rgb * c.a, c.a);\n"
	"}\n";

/* pass 2: the four source pixels of each 2x2 block (u_step = one texel), from the vertex shader */
static const char vs_blocks[] =
	"attribute vec2 a_pos;\n"
	"attribute vec2 a_tc;\n"
	"uniform vec2 u_step;\n"
	"varying vec2 v_p00;\n"
	"varying vec2 v_p10;\n"
	"varying vec2 v_p01;\n"
	"varying vec2 v_p11;\n"
	"void main() {\n"
	"  v_p00 = a_tc;\n"
	"  v_p10 = a_tc + vec2(u_step.x, 0.0);\n"
	"  v_p01 = a_tc + vec2(0.0, u_step.y);\n"
	"  v_p11 = a_tc + u_step;\n"
	"  gl_Position = vec4(a_pos, 0.0, 1.0);\n"
	"}\n";

static const char fs_blocks[] =
	"precision mediump float;\n"
	"uniform sampler2D u_idx;\n"
	"uniform sampler2D u_pal;\n"
	"varying vec2 v_p00;\n"
	"varying vec2 v_p10;\n"
	"varying vec2 v_p01;\n"
	"varying vec2 v_p11;\n"
	"void main() {\n"
	"  float i = texture2D(u_idx, v_p00).r;\n"
	"  if (i == texture2D(u_idx, v_p10).r && i == texture2D(u_idx, v_p01).r && i == texture2D(u_idx, v_p11).r) {\n"
	"    vec4 c = texture2D(u_pal, vec2(i * (255.0 / 256.0) + (0.5 / 256.0), 0.5));\n"
	"    gl_FragColor = c.a > 0.0 ? c : vec4(0.0);\n"
	"  } else\n"
	"    gl_FragColor = vec4(1.0, 1.0, 1.0, 0.0);\n"
	"}\n";

/* pass 3: v_tc = the bilinear sample point; v_t00 = the top-left tap, half a texel back, less 1/64 texel (u_back):
   when the tap falls exactly on a texel border (whole enlargements, e.g. 1280 -> 3840) the CPU takes the texel on the
   right (floor), and the 1/64 keeps the GPU there too, above the rounding of the interpolated coordinate (fp24 on
   Utgard: about 0.01 texel on a 1280 texel page) */
static const char vs_main[] =
	"attribute vec2 a_pos;\n"
	"attribute vec2 a_tc;\n"
	"uniform vec2 u_back;\n"
	"varying vec2 v_tc;\n"
	"varying vec2 v_t00;\n"
	"void main() { v_tc = a_tc; v_t00 = a_tc - u_back; gl_Position = vec4(a_pos, 0.0, 1.0); }\n";

/* sharp(v): the ramp steepened by u_k around 128/255 (as the CPU table), then smoothstep */
static const char fs_main[] =
	"precision mediump float;\n"
	"uniform sampler2D u_pm;\n"
	"uniform sampler2D u_blk;\n"
	"uniform float u_k;\n"
	"uniform vec2 u_l;\n"
	"uniform vec3 u_cmin;\n"
	"uniform vec3 u_cmax;\n"
	"varying vec2 v_tc;\n"
	"varying vec2 v_t00;\n"
	"float sharp(float v) {\n"
	"  float t = clamp(0.50196078 + (v - 0.50196078) * u_k, 0.0, 1.0);\n"
	"  return t * t * (3.0 - 2.0 * t);\n"
	"}\n"
	"void main() {\n"
	"  vec4 b = texture2D(u_blk, v_t00);\n"
	"  if (b.a > 0.0 || b.r < 0.5) { gl_FragColor = b.bgra; return; }\n"
	"  vec4 s = texture2D(u_pm, v_tc);\n"
	"  float as = sharp(s.a);\n"
	"  if (as < 0.5 / 255.0) { gl_FragColor = vec4(0.0); return; }\n"
	"  vec3 c = clamp(s.rgb / s.a, 0.0, 1.0);\n"
	"  float d = u_l.y - u_l.x;\n"
	"  if (d > 0.0) {\n"
	"    float lb = dot(c, vec3(0.30078125, 0.5859375, 0.11328125));\n"
	"    float lt = u_l.x + sharp(clamp((lb - u_l.x) / d, 0.0, 1.0)) * d;\n"
	"    if (lt > lb && u_l.y > lb) c += (u_cmax - c) * ((lt - lb) / (u_l.y - lb));\n"
	"    else if (lt < lb && lb > u_l.x) c += (u_cmin - c) * ((lb - lt) / (lb - u_l.x));\n"
	"  }\n"
	"  gl_FragColor = vec4(c.b, c.g, c.r, as);\n"
	"}\n";

/* probes only (Options::test_bad_shader): what reaches the compiler instead of fs_main */
static const char fs_broken[] = "precision mediump float;\nvoid main() { gl_FragColor = nu_exista; }\n";

/* the quad: position x, y and texture coordinate s, t; source row 0 = GL row 0 = the top row of the area */
static const GLfloat quad[16] = { -1, -1, 0, 0,  1, -1, 1, 0,  -1, 1, 0, 1,  1, 1, 1, 1 };

/* ------------------------------------------------------------------ small helpers */

static double nowMs()
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static bool exists(const char *path)
{
	return path && path[0] && (access(path, F_OK) == 0);
}

static void touch(const char *path)
{
	if (!path || !path[0])
		return;
	int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd >= 0)
		close(fd);
}

static void removeFile(const char *path)
{
	if (path && path[0])
		unlink(path);
}

static bool startsWithAny(const char *s, const char *const *prefixes, int n)
{
	for (int i = 0; i < n && prefixes[i]; ++i)
		if (!strncmp(s, prefixes[i], strlen(prefixes[i])))
			return true;
	return false;
}

/* how many descriptors and mappings of this process point to a framebuffer device */
static void countFramebuffer(const char *const *prefixes, int n, int &fds, int &maps)
{
	fds = maps = 0;
	DIR *d = opendir("/proc/self/fd");
	if (d)
	{
		struct dirent *e;
		while ((e = readdir(d)))
		{
			char target[PATH_MAX];
			if (e->d_name[0] == '.')
				continue;
			const ssize_t len = readlinkat(dirfd(d), e->d_name, target, sizeof(target) - 1);
			if (len <= 0)
				continue;
			target[len] = 0;
			if (startsWithAny(target, prefixes, n))
				++fds;
		}
		closedir(d);
	}
	FILE *f = fopen("/proc/self/maps", "re");
	if (f)
	{
		char line[512];
		while (fgets(line, sizeof(line), f))
		{
			const char *p = strchr(line, '/');
			if (p && startsWithAny(p, prefixes, n))
				++maps;
		}
		fclose(f);
	}
}

/*
 * libMali reads MALI_NEVERBLIT (and, on the framebuffer path, MALI_NOCLEAR) with getenv when EGL makes its main
 * context, i.e. at the first EGL call (libMali 20180830: __egl_get_main_context 0x77ca4..0x77d14). They are set just
 * before and put back right after eglInitialize, so programs started by enigma2 do not inherit them.
 * Before main (one thread) both get a place in the environment with "0", which for libMali is exactly like unset (it
 * acts on "1"/"TRUE", and for NOCLEAR on any value not starting with '0'): later they are only replaced in place,
 * which never reallocates the environment under a getenv of another thread (setenv of a new name would).
 */
static const char *const mali_env[2] = { "MALI_NEVERBLIT", "MALI_NOCLEAR" };

static struct MaliEnvReserve
{
	MaliEnvReserve()
	{
		for (int i = 0; i < 2; ++i)
			setenv(mali_env[i], "0", 0);
	}
} mali_env_reserve;

struct MaliEnv
{
	char *old[2];
	bool set;
	MaliEnv(): set(false) { old[0] = old[1] = 0; }
	void apply()
	{
		for (int i = 0; i < 2; ++i)
		{
			const char *v = getenv(mali_env[i]);
			old[i] = v ? strdup(v) : 0;
			setenv(mali_env[i], "1", 1);
		}
		set = true;
	}
	void restore()
	{
		if (!set)
			return;
		for (int i = 0; i < 2; ++i)
		{
			if (old[i])
				setenv(mali_env[i], old[i], 1);
			else
				unsetenv(mali_env[i]);
			free(old[i]);
			old[i] = 0;
		}
		set = false;
	}
	~MaliEnv() { restore(); }
};

/* ------------------------------------------------------------------ one job */

struct Job
{
	const unsigned char *src;	/* sw x sh palette indices, packed */
	int sw, sh;
	unsigned char pal[256][4];	/* R, G, B, A (A = opacity) */
	unsigned int src_gen;		/* the same number = the same source and palette as the job before */
	int vx, vy, pw, ph;		/* pos, relative to the area */
	int aw, ah;			/* the area */
	float k, lmin, lmax, cmin[3], cmax[3];
	uint32_t *out;			/* aw x ah, ARGB8888 */
};

enum { jobIdle = 0, jobFilling, jobQueued, jobRunning, jobDone, jobAbandoned };

class Gpu
{
public:
	Gpu();
	bool blit(gSurface *dst, const gSurface *src, const eRect &pos, const eRect &area);
	int getState();
	const char *getReason() { return m_reason; }
	void setOptions(const hdsgpu::Options &o);
	bool waitReady(int timeout_ms);
	void shutdown();

private:
	/* shared, under m_lock */
	pthread_mutex_t m_lock;
	pthread_cond_t m_cond;
	int m_state;
	char m_reason[256];
	int m_job_state, m_job_result;
	double m_job_ms;
	bool m_quit, m_thread_started;
	pthread_t m_thread;
	hdsgpu::Options m_opt;
	Job m_job;
	int m_timeouts_in_row;
	int m_max_tex, m_max_view;	/* GL limits, copied from the GPU thread when it is ready */
	/* statistics */
	unsigned long m_n_gpu, m_n_busy, m_n_not_ready, m_n_timeout, m_n_large;
	double m_gpu_ms_sum, m_gpu_ms_max, m_wait_ms_sum, m_wait_ms_max;
	char m_info[256];	/* libraries, renderer, start times */

	/* drawing thread only */
	unsigned char *m_src[2];
	size_t m_src_size[2];
	int m_src_cur, m_src_w, m_src_h;
	unsigned char m_prev_pal[256][4];
	unsigned int m_gen;
	uint32_t *m_out;
	size_t m_out_size;

	/* GPU thread only */
	Api m_api;
	void *m_egl_lib, *m_gles_lib;
	EGLDisplay m_dpy;
	EGLSurface m_srf;
	EGLContext m_ctx;
	GLuint m_p_pm, m_p_blk, m_p_main;
	GLint m_u_step, m_u_back, m_u_k, m_u_l, m_u_cmin, m_u_cmax;
	GLuint m_t_idx, m_t_pal, m_t_pm, m_t_blk, m_t_out;
	GLuint m_f_pm, m_f_blk, m_f_out;
	int m_tex_w, m_tex_h, m_out_w, m_out_h;
	unsigned int m_uploaded_gen;
	GLint m_gl_max_tex, m_gl_max_view;

	static void *threadEntry(void *self) { return ((Gpu *)self)->threadMain(); }
	void *threadMain();
	bool start(char *why, size_t n, char *info, size_t ninfo);
	bool startGl(char *why, size_t n, char *info, size_t ninfo);
	bool loadLibraries(char *why, size_t n);
	GLuint program(const char *vs, const char *fs, char *why, size_t n);
	GLuint texture(GLenum filter);
	bool attach(GLuint fbo, GLuint tex);
	bool selfTest(char *why, size_t n);
	int render(const Job &j, char *why, size_t n);
	void release();
	void setOff(const char *why);	/* under m_lock */
	void writeState();
	void writeOffFile(const char *why);
	int deadlineMs(int aw, int ah) const;
	void resetGl();
};

Gpu::Gpu()
{
	pthread_condattr_t ca;
	pthread_mutex_init(&m_lock, 0);
	pthread_condattr_init(&ca);
	pthread_condattr_setclock(&ca, CLOCK_MONOTONIC);
	pthread_cond_init(&m_cond, &ca);
	pthread_condattr_destroy(&ca);
	m_state = hdsgpu::stateIdle;
	m_reason[0] = 0;
	m_job_state = jobIdle;
	m_job_result = 0;
	m_job_ms = 0;
	m_quit = false;
	m_thread_started = false;
	m_opt = hdsgpu::defaultOptions();
	memset(&m_job, 0, sizeof(m_job));
	m_timeouts_in_row = 0;
	m_max_tex = m_max_view = 0;
	m_n_gpu = m_n_busy = m_n_not_ready = m_n_timeout = m_n_large = 0;
	m_gpu_ms_sum = m_gpu_ms_max = m_wait_ms_sum = m_wait_ms_max = 0;
	m_info[0] = 0;
	m_src[0] = m_src[1] = 0;
	m_src_size[0] = m_src_size[1] = 0;
	m_src_cur = 0;
	m_src_w = m_src_h = 0;
	memset(m_prev_pal, 0, sizeof(m_prev_pal));
	m_gen = 0;
	m_out = 0;
	m_out_size = 0;
	memset(&m_api, 0, sizeof(m_api));
	m_egl_lib = m_gles_lib = 0;
	resetGl();
}

void Gpu::resetGl()
{
	m_dpy = 0;
	m_srf = 0;
	m_ctx = 0;
	m_p_pm = m_p_blk = m_p_main = 0;
	m_u_step = m_u_back = m_u_k = m_u_l = m_u_cmin = m_u_cmax = -1;
	m_t_idx = m_t_pal = m_t_pm = m_t_blk = m_t_out = 0;
	m_f_pm = m_f_blk = m_f_out = 0;
	m_tex_w = m_tex_h = m_out_w = m_out_h = 0;
	m_uploaded_gen = 0;
	m_gl_max_tex = m_gl_max_view = 0;
}

int Gpu::getState()
{
	pthread_mutex_lock(&m_lock);
	int s = m_state;
	pthread_mutex_unlock(&m_lock);
	return s;
}

void Gpu::setOptions(const hdsgpu::Options &o)
{
	pthread_mutex_lock(&m_lock);
	if (m_state == hdsgpu::stateIdle)
		m_opt = o;
	else
		eWarning("[hdsgpu] options ignored: the GPU is already started");
	pthread_mutex_unlock(&m_lock);
}

void Gpu::setOff(const char *why)
{
	if (m_state == hdsgpu::stateOff)
		return;
	m_state = hdsgpu::stateOff;
	snprintf(m_reason, sizeof(m_reason), "%s", why);
	pthread_cond_broadcast(&m_cond);
}

int Gpu::deadlineMs(int aw, int ah) const
{
	long long ms = m_opt.deadline_ms + ((long long)m_opt.deadline_ms_per_mpixel * aw * ah) / 1000000;
	if (ms > m_opt.deadline_max_ms)
		ms = m_opt.deadline_max_ms;
	return ms < 1 ? 1 : (int)ms;
}

void Gpu::writeOffFile(const char *why)
{
	if (!m_opt.off_file || !m_opt.off_file[0])
		return;
	FILE *f = fopen(m_opt.off_file, "we");
	if (f)
	{
		fprintf(f, "%s\nSe sterge fisierul ca placa video sa fie incercata din nou.\n", why);
		fclose(f);
	}
}

/* the state for people (ssh: cat /tmp/hds-gpu.stare); rewritten at every change and every 32 pages */
void Gpu::writeState()
{
	char text[1024];
	pthread_mutex_lock(&m_lock);
	const char *word = m_state == hdsgpu::stateReady ? "gata" : (m_state == hdsgpu::stateStarting ? "pornire" :
		(m_state == hdsgpu::stateOff ? "oprit" : "nefolosit"));
	unsigned long cpu = m_n_busy + m_n_not_ready + m_n_timeout + m_n_large;
	snprintf(text, sizeof(text),
		"%s\n%s\n%s\n"
		"pagini pe GPU: %lu; pe procesor: %lu (GPU ocupat %lu, nepregatit %lu, termen depasit %lu, prea mare %lu)\n"
		"timp pe GPU: mediu %.2f ms, maxim %.2f ms; asteptare la desen: medie %.2f ms, maxima %.2f ms\n",
		word, m_reason[0] ? m_reason : "-", m_info[0] ? m_info : "-",
		m_n_gpu, cpu, m_n_busy, m_n_not_ready, m_n_timeout, m_n_large,
		m_n_gpu ? m_gpu_ms_sum / m_n_gpu : 0.0, m_gpu_ms_max,
		m_n_gpu ? m_wait_ms_sum / m_n_gpu : 0.0, m_wait_ms_max);
	const char *path = m_opt.state_file;
	pthread_mutex_unlock(&m_lock);
	if (!path || !path[0])
		return;
	FILE *f = fopen(path, "we");
	if (f)
	{
		fputs(text, f);
		fclose(f);
	}
}

/* ------------------------------------------------------------------ the GPU thread */

bool Gpu::loadLibraries(char *why, size_t n)
{
	m_egl_lib = m_gles_lib = 0;
	for (int i = 0; i < 3 && m_opt.egl_libs[i] && !m_egl_lib; ++i)
		m_egl_lib = dlopen(m_opt.egl_libs[i], RTLD_NOW | RTLD_LOCAL);
	if (!m_egl_lib)
	{
		const char *e = dlerror();
		snprintf(why, n, "biblioteca EGL lipseste (%s)", e ? e : "?");
		return false;
	}
	for (int i = 0; i < 3 && m_opt.gles_libs[i] && !m_gles_lib; ++i)
		m_gles_lib = dlopen(m_opt.gles_libs[i], RTLD_NOW | RTLD_LOCAL);
	if (!m_gles_lib)
	{
		const char *e = dlerror();
		snprintf(why, n, "biblioteca GLESv2 lipseste (%s)", e ? e : "?");
		return false;
	}
	/* the libraries stay loaded until the process ends (libMali is not made to be unloaded) */
	static_assert(sizeof(void *) == sizeof(void (*)()), "dlsym gives a data pointer");
	const char *missing = 0;
#define HDSGPU_LOAD(lib, name) \
	if (!missing) \
	{ \
		void *p = dlsym(lib, #name); \
		if (p) \
			memcpy(&m_api.name, &p, sizeof(p)); \
		else \
			missing = #name; \
	}
#define HDSGPU_LOAD_EGL(ret, name, args) HDSGPU_LOAD(m_egl_lib, name)
#define HDSGPU_LOAD_GL(ret, name, args) HDSGPU_LOAD(m_gles_lib, name)
	HDSGPU_EGL_FUNCTIONS(HDSGPU_LOAD_EGL)
	HDSGPU_GL_FUNCTIONS(HDSGPU_LOAD_GL)
#undef HDSGPU_LOAD_GL
#undef HDSGPU_LOAD_EGL
#undef HDSGPU_LOAD
	if (missing)
	{
		snprintf(why, n, "functia %s lipseste din biblioteca", missing);
		memset(&m_api, 0, sizeof(m_api));
		return false;
	}
	return true;
}

/* one line of a compiler log (the logs have new lines) */
static void oneLine(char *s)
{
	for (; *s; ++s)
		if ((*s == '\n') || (*s == '\r') || (*s == '\t'))
			*s = ' ';
}

GLuint Gpu::program(const char *vs, const char *fs, char *why, size_t n)
{
	const Api &a = m_api;
	const GLuint sh[2] = { a.glCreateShader(GLC_VERTEX_SHADER), a.glCreateShader(GLC_FRAGMENT_SHADER) };
	const char *src[2] = { vs, fs };
	for (int i = 0; i < 2; ++i)
	{
		GLint ok = 0;
		a.glShaderSource(sh[i], 1, &src[i], 0);
		a.glCompileShader(sh[i]);
		a.glGetShaderiv(sh[i], GLC_COMPILE_STATUS, &ok);
		if (!ok)
		{
			char log[200] = "";
			a.glGetShaderInfoLog(sh[i], sizeof(log), 0, log);
			oneLine(log);
			snprintf(why, n, "shaderul de %s nu se compileaza: %s", i ? "fragment" : "varfuri", log);
			a.glDeleteShader(sh[0]);
			a.glDeleteShader(sh[1]);
			return 0;
		}
	}
	const GLuint p = a.glCreateProgram();
	a.glAttachShader(p, sh[0]);
	a.glAttachShader(p, sh[1]);
	a.glBindAttribLocation(p, 0, "a_pos");
	a.glBindAttribLocation(p, 1, "a_tc");
	a.glLinkProgram(p);
	a.glDeleteShader(sh[0]);	/* freed with the program */
	a.glDeleteShader(sh[1]);
	GLint ok = 0;
	a.glGetProgramiv(p, GLC_LINK_STATUS, &ok);
	if (!ok)
	{
		char log[200] = "";
		a.glGetProgramInfoLog(p, sizeof(log), 0, log);
		oneLine(log);
		snprintf(why, n, "programul nu se leaga: %s", log);
		return 0;
	}
	return p;
}

GLuint Gpu::texture(GLenum filter)
{
	const Api &a = m_api;
	GLuint t = 0;
	a.glGenTextures(1, &t);
	a.glBindTexture(GLC_TEXTURE_2D, t);
	a.glTexParameteri(GLC_TEXTURE_2D, GLC_TEXTURE_MIN_FILTER, filter);
	a.glTexParameteri(GLC_TEXTURE_2D, GLC_TEXTURE_MAG_FILTER, filter);
	a.glTexParameteri(GLC_TEXTURE_2D, GLC_TEXTURE_WRAP_S, GLC_CLAMP_TO_EDGE);
	a.glTexParameteri(GLC_TEXTURE_2D, GLC_TEXTURE_WRAP_T, GLC_CLAMP_TO_EDGE);
	return t;
}

bool Gpu::attach(GLuint fbo, GLuint tex)
{
	m_api.glBindFramebuffer(GLC_FRAMEBUFFER, fbo);
	m_api.glFramebufferTexture2D(GLC_FRAMEBUFFER, GLC_COLOR_ATTACHMENT0, GLC_TEXTURE_2D, tex, 0);
	return m_api.glCheckFramebufferStatus(GLC_FRAMEBUFFER) == GLC_FRAMEBUFFER_COMPLETE;
}

/* The page's parameters, as blit_scaled_sharp_8 computes them: the darkest and the lightest visible colour among the
   first `range` palette entries, and the steepness k = 256 * enlargement of the dominant side (8.8, truncated). */
static void pageParams(const unsigned char pal[256][4], int range, int sw, int sh, int pw, int ph, Job &j)
{
	int lmin = 256, lmax = -1, cmin[3] = { 0, 0, 0 }, cmax[3] = { 0, 0, 0 };
	for (int i = 0; i < range && i < 256; ++i)
	{
		if (!pal[i][3])
			continue;
		const int l = (pal[i][0] * 77 + pal[i][1] * 150 + pal[i][2] * 29) >> 8;
		if (l < lmin)
		{
			lmin = l;
			for (int c = 0; c < 3; ++c)
				cmin[c] = pal[i][c];
		}
		if (l > lmax)
		{
			lmax = l;
			for (int c = 0; c < 3; ++c)
				cmax[c] = pal[i][c];
		}
	}
	j.lmin = (lmax > lmin) ? lmin / 255.0f : 0.0f;
	j.lmax = (lmax > lmin) ? lmax / 255.0f : 0.0f;
	for (int c = 0; c < 3; ++c)
	{
		j.cmin[c] = cmin[c] / 255.0f;
		j.cmax[c] = cmax[c] / 255.0f;
	}
	const bool wide = (long long)pw * sh > (long long)ph * sw;
	j.k = (float)((256LL * (wide ? pw : ph)) / (wide ? sw : sh)) / 256.0f;
}

/* 0 = the area is in j.out; otherwise why says what failed and the GPU is given up */
int Gpu::render(const Job &j, char *why, size_t n)
{
	const Api &a = m_api;
	a.glDisable(GLC_SCISSOR_TEST);
	if (!m_uploaded_gen || (j.src_gen != m_uploaded_gen))
	{
		m_uploaded_gen = 0;
		a.glActiveTexture(GLC_TEXTURE0);
		a.glBindTexture(GLC_TEXTURE_2D, m_t_idx);
		if ((j.sw != m_tex_w) || (j.sh != m_tex_h))
		{
			a.glTexImage2D(GLC_TEXTURE_2D, 0, GLC_LUMINANCE, j.sw, j.sh, 0, GLC_LUMINANCE, GLC_UNSIGNED_BYTE, j.src);
			a.glBindTexture(GLC_TEXTURE_2D, m_t_pm);
			a.glTexImage2D(GLC_TEXTURE_2D, 0, GLC_RGBA, j.sw, j.sh, 0, GLC_RGBA, GLC_UNSIGNED_BYTE, 0);
			a.glBindTexture(GLC_TEXTURE_2D, m_t_blk);
			a.glTexImage2D(GLC_TEXTURE_2D, 0, GLC_RGBA, j.sw, j.sh, 0, GLC_RGBA, GLC_UNSIGNED_BYTE, 0);
			if (!attach(m_f_pm, m_t_pm) || !attach(m_f_blk, m_t_blk))
			{
				snprintf(why, n, "FBO incomplet la %dx%d", j.sw, j.sh);
				m_tex_w = m_tex_h = 0;
				return -1;
			}
			m_tex_w = j.sw;
			m_tex_h = j.sh;
			a.glBindTexture(GLC_TEXTURE_2D, m_t_idx);
		}
		else
			a.glTexSubImage2D(GLC_TEXTURE_2D, 0, 0, 0, j.sw, j.sh, GLC_LUMINANCE, GLC_UNSIGNED_BYTE, j.src);
		a.glActiveTexture(GLC_TEXTURE1);
		a.glBindTexture(GLC_TEXTURE_2D, m_t_pal);
		a.glTexSubImage2D(GLC_TEXTURE_2D, 0, 0, 0, 256, 1, GLC_RGBA, GLC_UNSIGNED_BYTE, j.pal);
		a.glViewport(0, 0, j.sw, j.sh);
		/* pass 1: premultiplied colour */
		a.glBindFramebuffer(GLC_FRAMEBUFFER, m_f_pm);
		a.glUseProgram(m_p_pm);
		a.glDrawArrays(GLC_TRIANGLE_STRIP, 0, 4);
		/* pass 2: the 2x2 blocks that keep their palette colour */
		a.glBindFramebuffer(GLC_FRAMEBUFFER, m_f_blk);
		a.glUseProgram(m_p_blk);
		a.glUniform2f(m_u_step, 1.0f / j.sw, 1.0f / j.sh);
		a.glDrawArrays(GLC_TRIANGLE_STRIP, 0, 4);
	}
	if ((j.aw > m_out_w) || (j.ah > m_out_h))
	{
		const int w = (j.aw > m_out_w) ? j.aw : m_out_w, h = (j.ah > m_out_h) ? j.ah : m_out_h;
		a.glActiveTexture(GLC_TEXTURE0);
		a.glBindTexture(GLC_TEXTURE_2D, m_t_out);
		a.glTexImage2D(GLC_TEXTURE_2D, 0, GLC_RGBA, w, h, 0, GLC_RGBA, GLC_UNSIGNED_BYTE, 0);
		if (!attach(m_f_out, m_t_out))
		{
			snprintf(why, n, "FBO incomplet la %dx%d", w, h);
			m_out_w = m_out_h = 0;
			return -1;
		}
		m_out_w = w;
		m_out_h = h;
	}
	/* pass 3: the area; the viewport is pos (it may go past the texture, GL cuts it), the scissor the area */
	a.glBindFramebuffer(GLC_FRAMEBUFFER, m_f_out);
	a.glViewport(j.vx, j.vy, j.pw, j.ph);
	a.glEnable(GLC_SCISSOR_TEST);
	a.glScissor(0, 0, j.aw, j.ah);
	a.glUseProgram(m_p_main);
	a.glUniform2f(m_u_back, (0.5f - 1.0f / 64) / j.sw, (0.5f - 1.0f / 64) / j.sh);
	a.glUniform1f(m_u_k, j.k);
	a.glUniform2f(m_u_l, j.lmin, j.lmax);
	a.glUniform3f(m_u_cmin, j.cmin[0], j.cmin[1], j.cmin[2]);
	a.glUniform3f(m_u_cmax, j.cmax[0], j.cmax[1], j.cmax[2]);
	a.glActiveTexture(GLC_TEXTURE0);
	a.glBindTexture(GLC_TEXTURE_2D, m_t_pm);
	a.glActiveTexture(GLC_TEXTURE1);
	a.glBindTexture(GLC_TEXTURE_2D, m_t_blk);
	a.glDrawArrays(GLC_TRIANGLE_STRIP, 0, 4);
	a.glReadPixels(0, 0, j.aw, j.ah, GLC_RGBA, GLC_UNSIGNED_BYTE, j.out);
	a.glDisable(GLC_SCISSOR_TEST);
	const GLenum e = a.glGetError();
	if (e != GLC_NO_ERROR)
	{
		snprintf(why, n, "eroare GL 0x%04x (sursa %dx%d, zona %dx%d)", e, j.sw, j.sh, j.aw, j.ah);
		m_tex_w = m_tex_h = 0;
		return -1;
	}
	m_uploaded_gen = j.src_gen;
	return 0;
}

/* A page 8x8 with four quarters (red, blue / green, transparent) made 24x24: the middle of each quarter must be its
   exact palette colour (the kept 2x2 blocks), which catches the byte order B,G,R,A, a flip, and the palette lookup. */
bool Gpu::selfTest(char *why, size_t n)
{
	static unsigned char page[8 * 8];
	uint32_t out[24 * 24];
	Job j;
	memset(&j, 0, sizeof(j));
	for (int y = 0; y < 8; ++y)
		for (int x = 0; x < 8; ++x)
			page[y * 8 + x] = (y < 4) ? ((x < 4) ? 1 : 2) : ((x < 4) ? 3 : 0);
	j.pal[1][0] = 255;
	j.pal[1][3] = 255;
	j.pal[2][2] = 255;
	j.pal[2][3] = 255;
	j.pal[3][1] = 255;
	j.pal[3][3] = 255;
	j.src = page;
	j.sw = j.sh = 8;
	j.src_gen = 0xFFFFFFFFu;	/* never the number of a real page */
	j.pw = j.ph = j.aw = j.ah = 24;
	j.out = out;
	pageParams(j.pal, 256, 8, 8, 24, 24, j);
	memset(out, 0x55, sizeof(out));
	if (render(j, why, n))
		return false;
	static const struct { int x, y; uint32_t c; } want[4] = {
		{ 3, 3, 0xFFFF0000u }, { 20, 3, 0xFF0000FFu }, { 3, 20, 0xFF00FF00u }, { 20, 20, 0 } };
	for (int i = 0; i < 4; ++i)
	{
		const uint32_t got = out[want[i].y * 24 + want[i].x];
		if (got != want[i].c)
		{
			snprintf(why, n, "proba de la pornire: punctul (%d,%d) = 0x%08x, trebuia 0x%08x", want[i].x, want[i].y,
				(unsigned int)got, (unsigned int)want[i].c);
			return false;
		}
	}
	return true;
}

bool Gpu::startGl(char *why, size_t n, char *info, size_t ninfo)
{
	const double t0 = nowMs();
	MaliEnv env;
	if (!m_opt.test_no_mali_env)
		env.apply();	/* before the first EGL call: libMali reads them when it makes its main context */
	if (!loadLibraries(why, n))
		return false;
	const Api &a = m_api;
	const double t1 = nowMs();
	int n_fb = 0;
	while ((n_fb < 3) && m_opt.fb_prefixes[n_fb])
		++n_fb;
	int fds0 = 0, maps0 = 0, fds1 = 0, maps1 = 0;
	countFramebuffer(m_opt.fb_prefixes, n_fb, fds0, maps0);
	m_dpy = a.eglGetDisplay(0);	/* EGL_DEFAULT_DISPLAY; with MALI_NEVERBLIT=1 a display without /dev/fb */
	if (!m_dpy)
	{
		snprintf(why, n, "eglGetDisplay a esuat (0x%04x)", (unsigned int)a.eglGetError());
		return false;
	}
	EGLint major = 0, minor = 0;
	if (!a.eglInitialize(m_dpy, &major, &minor))
	{
		snprintf(why, n, "eglInitialize a esuat (0x%04x)", (unsigned int)a.eglGetError());
		m_dpy = 0;
		return false;
	}
	env.restore();
	countFramebuffer(m_opt.fb_prefixes, n_fb, fds1, maps1);
	if ((fds1 > fds0) || (maps1 > maps0))
	{
		snprintf(why, n, "biblioteca a deschis framebuffer-ul (descriptori %d -> %d, mapari %d -> %d)", fds0, fds1,
			maps0, maps1);
		return false;
	}
	const double t2 = nowMs();
	static const EGLint config_attribs[] = { EGLC_SURFACE_TYPE, EGLC_PBUFFER_BIT, EGLC_RENDERABLE_TYPE,
		EGLC_OPENGL_ES2_BIT, EGLC_RED_SIZE, 8, EGLC_GREEN_SIZE, 8, EGLC_BLUE_SIZE, 8, EGLC_ALPHA_SIZE, 8, EGLC_NONE };
	static const EGLint pbuffer_attribs[] = { EGLC_WIDTH, 16, EGLC_HEIGHT, 16, EGLC_NONE };
	static const EGLint context_attribs[] = { EGLC_CONTEXT_CLIENT_VERSION, 2, EGLC_NONE };
	EGLConfig config = 0;
	EGLint count = 0;
	if (!a.eglChooseConfig(m_dpy, config_attribs, &config, 1, &count) || (count < 1))
	{
		snprintf(why, n, "nicio configuratie EGL RGBA8888 cu pbuffer si GLES2 (0x%04x)", (unsigned int)a.eglGetError());
		return false;
	}
	m_srf = a.eglCreatePbufferSurface(m_dpy, config, pbuffer_attribs);
	if (!m_srf)
	{
		snprintf(why, n, "eglCreatePbufferSurface a esuat (0x%04x)", (unsigned int)a.eglGetError());
		return false;
	}
	a.eglBindAPI(EGLC_OPENGL_ES_API);
	m_ctx = a.eglCreateContext(m_dpy, config, 0, context_attribs);
	if (!m_ctx)
	{
		snprintf(why, n, "eglCreateContext a esuat (0x%04x)", (unsigned int)a.eglGetError());
		return false;
	}
	if (!a.eglMakeCurrent(m_dpy, m_srf, m_srf, m_ctx))
	{
		snprintf(why, n, "eglMakeCurrent a esuat (0x%04x)", (unsigned int)a.eglGetError());
		return false;
	}
	const char *version = (const char *)a.glGetString(GLC_VERSION);
	const char *renderer = (const char *)a.glGetString(GLC_RENDERER);
	if (!version || strncmp(version, "OpenGL ES ", 10))
	{
		snprintf(why, n, "contextul nu e OpenGL ES (%s)", version ? version : "?");
		return false;
	}
	GLint view[2] = { 0, 0 };
	a.glGetIntegerv(GLC_MAX_TEXTURE_SIZE, &m_gl_max_tex);
	a.glGetIntegerv(GLC_MAX_VIEWPORT_DIMS, view);
	m_gl_max_view = (view[0] < view[1]) ? view[0] : view[1];
	const double t3 = nowMs();
	m_p_pm = program(vs_plain, fs_premultiply, why, n);
	if (!m_p_pm)
		return false;
	m_p_blk = program(vs_blocks, fs_blocks, why, n);
	if (!m_p_blk)
		return false;
	m_p_main = program(vs_main, m_opt.test_bad_shader ? fs_broken : fs_main, why, n);
	if (!m_p_main)
		return false;
	a.glUseProgram(m_p_pm);
	a.glUniform1i(a.glGetUniformLocation(m_p_pm, "u_idx"), 0);
	a.glUniform1i(a.glGetUniformLocation(m_p_pm, "u_pal"), 1);
	a.glUseProgram(m_p_blk);
	a.glUniform1i(a.glGetUniformLocation(m_p_blk, "u_idx"), 0);
	a.glUniform1i(a.glGetUniformLocation(m_p_blk, "u_pal"), 1);
	m_u_step = a.glGetUniformLocation(m_p_blk, "u_step");
	a.glUseProgram(m_p_main);
	a.glUniform1i(a.glGetUniformLocation(m_p_main, "u_pm"), 0);
	a.glUniform1i(a.glGetUniformLocation(m_p_main, "u_blk"), 1);
	m_u_back = a.glGetUniformLocation(m_p_main, "u_back");
	m_u_k = a.glGetUniformLocation(m_p_main, "u_k");
	m_u_l = a.glGetUniformLocation(m_p_main, "u_l");
	m_u_cmin = a.glGetUniformLocation(m_p_main, "u_cmin");
	m_u_cmax = a.glGetUniformLocation(m_p_main, "u_cmax");
	if ((m_u_step < 0) || (m_u_back < 0) || (m_u_k < 0) || (m_u_l < 0) || (m_u_cmin < 0) || (m_u_cmax < 0))
	{
		snprintf(why, n, "uniforme lipsa din programe");
		return false;
	}
	a.glDisable(GLC_DITHER);
	a.glDisable(GLC_BLEND);
	a.glDisable(GLC_DEPTH_TEST);
	a.glDisable(GLC_STENCIL_TEST);
	a.glDisable(GLC_CULL_FACE);
	a.glPixelStorei(GLC_UNPACK_ALIGNMENT, 1);
	a.glPixelStorei(GLC_PACK_ALIGNMENT, 4);
	a.glVertexAttribPointer(0, 2, GLC_FLOAT, 0, 4 * sizeof(GLfloat), quad);
	a.glVertexAttribPointer(1, 2, GLC_FLOAT, 0, 4 * sizeof(GLfloat), quad + 2);
	a.glEnableVertexAttribArray(0);
	a.glEnableVertexAttribArray(1);
	m_t_idx = texture(GLC_NEAREST);
	m_t_pal = texture(GLC_NEAREST);
	a.glTexImage2D(GLC_TEXTURE_2D, 0, GLC_RGBA, 256, 1, 0, GLC_RGBA, GLC_UNSIGNED_BYTE, 0);
	m_t_pm = texture(GLC_LINEAR);
	m_t_blk = texture(GLC_NEAREST);
	m_t_out = texture(GLC_NEAREST);
	a.glGenFramebuffers(1, &m_f_pm);
	a.glGenFramebuffers(1, &m_f_blk);
	a.glGenFramebuffers(1, &m_f_out);
	GLenum e = a.glGetError();
	if (e != GLC_NO_ERROR)
	{
		snprintf(why, n, "eroare GL 0x%04x la pregatire", e);
		return false;
	}
	const double t4 = nowMs();
	if (!selfTest(why, n))
		return false;
	const double t5 = nowMs();
	snprintf(info, ninfo, "%s | %s | EGL %d.%d | pornire %.1f ms (biblioteci %.1f, EGL %.1f, context %.1f, "
		"programe %.1f, proba %.1f)", renderer ? renderer : "?", version, (int)major, (int)minor, t5 - t0, t1 - t0,
		t2 - t1, t3 - t2, t4 - t3, t5 - t4);
	return true;
}

bool Gpu::start(char *why, size_t n, char *info, size_t ninfo)
{
	if (exists(m_opt.off_file))
	{
		snprintf(why, n, "oprit de fisierul %s", m_opt.off_file);
		return false;
	}
	if (exists(m_opt.job_mark))
	{
		snprintf(why, n, "enigma2 s-a oprit in timpul unei lucrari pe placa video (a ramas %s)", m_opt.job_mark);
		writeOffFile(why);
		removeFile(m_opt.job_mark);
		return false;
	}
	if (exists(m_opt.start_mark))
	{
		snprintf(why, n, "pornirea placii video de data trecuta nu s-a terminat (a ramas %s)", m_opt.start_mark);
		writeOffFile(why);
		removeFile(m_opt.start_mark);
		return false;
	}
	touch(m_opt.start_mark);
	const bool ok = startGl(why, n, info, ninfo);
	if (!ok)
		release();
	removeFile(m_opt.start_mark);	/* a clean failure is not a crash: the next start may try again */
	return ok;
}

void Gpu::release()
{
	const Api &a = m_api;
	if (m_dpy && a.eglMakeCurrent)
	{
		a.eglMakeCurrent(m_dpy, 0, 0, 0);
		if (m_ctx)
			a.eglDestroyContext(m_dpy, m_ctx);
		if (m_srf)
			a.eglDestroySurface(m_dpy, m_srf);
		a.eglTerminate(m_dpy);
	}
	if (a.eglReleaseThread)
		a.eglReleaseThread();
	resetGl();
}

void *Gpu::threadMain()
{
	char why[256] = "", info[256] = "";
	const bool ok = start(why, sizeof(why), info, sizeof(info));
	pthread_mutex_lock(&m_lock);
	snprintf(m_info, sizeof(m_info), "%s", info);
	bool run = false;
	if (!ok)
		setOff(why);
	else if (!m_quit && (m_state == hdsgpu::stateStarting))
	{
		m_state = hdsgpu::stateReady;
		m_max_tex = m_gl_max_tex;
		m_max_view = m_gl_max_view;
		run = true;
		pthread_cond_broadcast(&m_cond);
	}
	pthread_mutex_unlock(&m_lock);
	if (ok)
		eDebug("[hdsgpu] ready: %s", info);
	else
		eWarning("[hdsgpu] the GPU is not used: %s", why);
	writeState();
	while (run)
	{
		pthread_mutex_lock(&m_lock);
		while ((m_job_state != jobQueued) && !m_quit && (m_state == hdsgpu::stateReady))
			pthread_cond_wait(&m_cond, &m_lock);
		if (m_quit || (m_state != hdsgpu::stateReady))
		{
			pthread_mutex_unlock(&m_lock);
			break;
		}
		m_job_state = jobRunning;
		const Job j = m_job;
		const int delay = m_opt.test_delay_ms;
		const char *mark = m_opt.job_mark;
		pthread_mutex_unlock(&m_lock);
		if (delay > 0)
			usleep(delay * 1000);
		touch(mark);
		const double t0 = nowMs();
		const int r = render(j, why, sizeof(why));
		const double t1 = nowMs();
		removeFile(mark);
		pthread_mutex_lock(&m_lock);
		if (m_job_state == jobAbandoned)
			m_job_state = jobIdle;
		else
		{
			m_job_state = jobDone;
			m_job_result = r;
		}
		m_job_ms = t1 - t0;
		if (r)
			setOff(why);
		pthread_cond_broadcast(&m_cond);
		pthread_mutex_unlock(&m_lock);
		if (r)
		{
			eWarning("[hdsgpu] the GPU is given up: %s", why);
			writeState();
			break;
		}
	}
	release();
	return 0;
}

/* ------------------------------------------------------------------ the drawing thread */

bool Gpu::blit(gSurface *dst, const gSurface *src, const eRect &pos, const eRect &area)
{
#if BYTE_ORDER != LITTLE_ENDIAN
	return false;	/* the GPU writes the bytes B, G, R, A: enigma2's 32 bit ARGB only on little endian */
#endif
	const int sw = src->x, sh = src->y, pw = pos.width(), ph = pos.height(), aw = area.width(), ah = area.height();
	if ((src->bpp != 8) || (dst->bpp != 32) || !src->data || !dst->data || (sw < 1) || (sh < 1) || (pw < 1) ||
			(ph < 1) || (aw < 1) || (ah < 1))
		return false;
	if ((area.left() < pos.left()) || (area.top() < pos.top()) || (area.right() > pos.right()) ||
			(area.bottom() > pos.bottom()) || (area.left() < 0) || (area.top() < 0) || (area.right() > dst->x) ||
			(area.bottom() > dst->y))
		return false;

	pthread_mutex_lock(&m_lock);
	if (m_state == hdsgpu::stateIdle)
	{
		/* the first page: the GPU starts in the background, this page is drawn by the CPU */
		m_state = hdsgpu::stateStarting;
		m_quit = false;
		if (pthread_create(&m_thread, 0, threadEntry, this) == 0)
			m_thread_started = true;
		else
			setOff("firul placii video nu s-a putut porni");
		pthread_mutex_unlock(&m_lock);
		writeState();
		return false;
	}
	if (m_state != hdsgpu::stateReady)
	{
		++m_n_not_ready;
		pthread_mutex_unlock(&m_lock);
		return false;
	}
	if ((sw > m_max_tex) || (sh > m_max_tex) || (aw > m_max_tex) || (ah > m_max_tex) || (pw > m_max_view) ||
			(ph > m_max_view) || ((long long)aw * ah > 4LL * 1024 * 1024))
	{
		++m_n_large;
		pthread_mutex_unlock(&m_lock);
		return false;
	}
	if (m_job_state != jobIdle)
	{
		++m_n_busy;
		pthread_mutex_unlock(&m_lock);
		return false;
	}
	m_job_state = jobFilling;	/* the GPU thread waits for jobQueued: the job and the buffers are ours now */
	const int wait_ms = deadlineMs(aw, ah);
	pthread_mutex_unlock(&m_lock);

	const double t0 = nowMs();
	const size_t need = (size_t)sw * sh, out_need = (size_t)aw * ah;
	const int slot = 1 - m_src_cur;	/* the buffer that does not hold the page before */
	if (m_src_size[slot] < need)
	{
		free(m_src[slot]);
		m_src[slot] = (unsigned char *)malloc(need);
		m_src_size[slot] = m_src[slot] ? need : 0;
	}
	if (m_out_size < out_need)
	{
		free(m_out);
		m_out = (uint32_t *)malloc(out_need * sizeof(uint32_t));
		m_out_size = m_out ? out_need : 0;
	}
	if (!m_src[slot] || !m_out)
	{
		pthread_mutex_lock(&m_lock);
		m_job_state = jobIdle;
		pthread_mutex_unlock(&m_lock);
		return false;
	}
	/* rows copied once (the page may be in uncached framebuffer memory), packed as GL wants them */
	for (int y = 0; y < sh; ++y)
		memcpy(m_src[slot] + (size_t)y * sw, (const unsigned char *)src->data + (size_t)y * src->stride, sw);
	Job &j = m_job;
	/* the palette as blit_scaled_sharp_8 reads it: clut a is transparency; past the clut, opaque grey */
	for (int i = 0; i < 256; ++i)
	{
		uint32_t c;
		if (src->clut.data && (i < src->clut.colors))
			c = ((uint32_t)src->clut.data[i].a << 24) | ((uint32_t)src->clut.data[i].r << 16) |
				((uint32_t)src->clut.data[i].g << 8) | (uint32_t)src->clut.data[i].b;
		else
			c = 0x010101 * i;
		c ^= 0xFF000000;
		j.pal[i][0] = (c >> 16) & 0xFF;
		j.pal[i][1] = (c >> 8) & 0xFF;
		j.pal[i][2] = c & 0xFF;
		j.pal[i][3] = c >> 24;
	}
	pageParams(j.pal, (src->clut.data && (src->clut.colors < 256)) ? src->clut.colors : 256, sw, sh, pw, ph, j);
	const bool same = (sw == m_src_w) && (sh == m_src_h) && m_src[m_src_cur] &&
		!memcmp(m_src[slot], m_src[m_src_cur], need) && !memcmp(j.pal, m_prev_pal, sizeof(m_prev_pal));
	if (!same)
	{
		m_src_cur = slot;
		m_src_w = sw;
		m_src_h = sh;
		memcpy(m_prev_pal, j.pal, sizeof(m_prev_pal));
		if ((++m_gen == 0) || (m_gen == 0xFFFFFFFFu))
			m_gen = 1;
	}
	j.src = m_src[m_src_cur];
	j.sw = sw;
	j.sh = sh;
	j.src_gen = m_gen;
	j.vx = pos.left() - area.left();
	j.vy = pos.top() - area.top();
	j.pw = pw;
	j.ph = ph;
	j.aw = aw;
	j.ah = ah;
	j.out = m_out;

	struct timespec until;
	clock_gettime(CLOCK_MONOTONIC, &until);
	until.tv_sec += wait_ms / 1000;
	until.tv_nsec += (long)(wait_ms % 1000) * 1000000L;
	if (until.tv_nsec >= 1000000000L)
	{
		until.tv_sec += 1;
		until.tv_nsec -= 1000000000L;
	}
	pthread_mutex_lock(&m_lock);
	m_job_state = jobQueued;
	pthread_cond_broadcast(&m_cond);
	while (((m_job_state == jobQueued) || (m_job_state == jobRunning)) && (m_state == hdsgpu::stateReady))
		if (pthread_cond_timedwait(&m_cond, &m_lock, &until) == ETIMEDOUT)
			break;
	if (m_job_state == jobDone)
	{
		if (m_job_result)
		{
			m_job_state = jobIdle;	/* the GPU thread gave up (m_state is off) */
			pthread_mutex_unlock(&m_lock);
			writeState();
			return false;
		}
	}
	else
	{
		if (m_job_state == jobQueued)
			m_job_state = jobIdle;	/* never taken: the GPU thread is gone or stuck elsewhere */
		else if (m_job_state == jobRunning)
			m_job_state = jobAbandoned;	/* the GPU thread finishes it into its buffer, nobody reads it */
		bool off = false;
		if (m_state == hdsgpu::stateReady)
		{
			++m_n_timeout;
			if (++m_timeouts_in_row >= m_opt.max_timeouts)
			{
				char why[128];
				snprintf(why, sizeof(why), "termen depasit de %d ori la rand (%d ms)", m_timeouts_in_row, wait_ms);
				setOff(why);
				off = true;
			}
		}
		pthread_mutex_unlock(&m_lock);
		if (off)
		{
			eWarning("[hdsgpu] the GPU is given up: %s", m_reason);
			writeState();
		}
		return false;
	}
	m_job_state = jobFilling;	/* copying out: the GPU thread takes nothing new */
	m_timeouts_in_row = 0;
	const double gpu_ms = m_job_ms;
	pthread_mutex_unlock(&m_lock);

	for (int y = 0; y < ah; ++y)
		memcpy((unsigned char *)dst->data + (size_t)(area.top() + y) * dst->stride + (size_t)area.left() * 4,
			m_out + (size_t)y * aw, (size_t)aw * 4);

	const double wait = nowMs() - t0;
	pthread_mutex_lock(&m_lock);
	m_job_state = jobIdle;
	++m_n_gpu;
	m_gpu_ms_sum += gpu_ms;
	if (gpu_ms > m_gpu_ms_max)
		m_gpu_ms_max = gpu_ms;
	m_wait_ms_sum += wait;
	if (wait > m_wait_ms_max)
		m_wait_ms_max = wait;
	const bool report = (m_n_gpu & 31) == 1;
	pthread_mutex_unlock(&m_lock);
	if (report)
		writeState();
	return true;
}

bool Gpu::waitReady(int timeout_ms)
{
	struct timespec until;
	clock_gettime(CLOCK_MONOTONIC, &until);
	until.tv_sec += timeout_ms / 1000;
	until.tv_nsec += (long)(timeout_ms % 1000) * 1000000L;
	if (until.tv_nsec >= 1000000000L)
	{
		until.tv_sec += 1;
		until.tv_nsec -= 1000000000L;
	}
	pthread_mutex_lock(&m_lock);
	while (m_state == hdsgpu::stateStarting)
		if (pthread_cond_timedwait(&m_cond, &m_lock, &until) == ETIMEDOUT)
			break;
	const bool ready = m_state == hdsgpu::stateReady;
	pthread_mutex_unlock(&m_lock);
	return ready;
}

void Gpu::shutdown()
{
	pthread_mutex_lock(&m_lock);
	m_quit = true;
	pthread_cond_broadcast(&m_cond);
	const bool started = m_thread_started;
	pthread_mutex_unlock(&m_lock);
	if (started)
		pthread_join(m_thread, 0);
	pthread_mutex_lock(&m_lock);
	m_thread_started = false;
	m_quit = false;
	m_state = hdsgpu::stateIdle;
	m_reason[0] = 0;
	m_info[0] = 0;
	m_job_state = jobIdle;
	m_job_result = 0;
	m_timeouts_in_row = 0;
	m_max_tex = m_max_view = 0;
	m_n_gpu = m_n_busy = m_n_not_ready = m_n_timeout = m_n_large = 0;
	m_gpu_ms_sum = m_gpu_ms_max = m_wait_ms_sum = m_wait_ms_max = 0;
	pthread_mutex_unlock(&m_lock);
	for (int i = 0; i < 2; ++i)
	{
		free(m_src[i]);
		m_src[i] = 0;
		m_src_size[i] = 0;
	}
	free(m_out);
	m_out = 0;
	m_out_size = 0;
	m_src_cur = 0;
	m_src_w = m_src_h = 0;
	m_gen = 0;
}

/* never destroyed: the GPU thread may still be inside the library when the process exits */
static Gpu &gpu()
{
	static Gpu *g = new Gpu;
	return *g;
}

}

namespace hdsgpu
{

bool blitScaled8(gSurface *dst, const gSurface *src, const eRect &pos, const eRect &area)
{
	return gpu().blit(dst, src, pos, area);
}

int state()
{
	return gpu().getState();
}

const char *stateReason()
{
	return gpu().getReason();
}

Options defaultOptions()
{
	Options o;
	memset(&o, 0, sizeof(o));
	o.egl_libs[0] = "libEGL.so.1";	/* on the u57: libEGL.so.1 -> libEGL.so.1.4 -> libMali.so */
	o.egl_libs[1] = "libEGL.so";
	o.gles_libs[0] = "libGLESv2.so.2";	/* libGLESv2.so.2 -> libGLESv2.so.2.0 -> libMali.so */
	o.gles_libs[1] = "libGLESv2.so";
	o.off_file = "/etc/enigma2/hds-fara-gpu";
	o.start_mark = "/etc/enigma2/hds-gpu.pornire";
	o.job_mark = "/tmp/hds-gpu.lucru";
	o.state_file = "/tmp/hds-gpu.stare";
	o.fb_prefixes[0] = "/dev/fb";
	o.fb_prefixes[1] = "/dev/graphics/fb";
	o.deadline_ms = 60;
	o.deadline_ms_per_mpixel = 40;
	o.deadline_max_ms = 250;
	o.max_timeouts = 3;
	return o;
}

void setOptions(const Options &options)
{
	gpu().setOptions(options);
}

bool waitReady(int timeout_ms)
{
	return gpu().waitReady(timeout_ms);
}

void shutdown()
{
	gpu().shutdown();
}

}
