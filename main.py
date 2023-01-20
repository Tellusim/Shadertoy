#!/usr/bin/env python3

# MIT License
# 
# Copyright (C) 2018-2023, Tellusim Technologies Inc. https://tellusim.com/
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import sys

from tellusimd import *

#
# Parameters
#
NumChannels = 4
path = '../data/'
names = [
	'3dG3WV.json',
	'ld3Gz2.json',
	'4tByz3.json',
	'MdX3Rr.json',
	'XslGRr.json',
	'lsf3zr.json',
	'Msj3zD.json',
]

#names = os.listdir(path)

#
# RenderPass
#
class RenderPass:
	def __init__(self):
		self.type = ''
		self.inputs = []
		self.outputs = []
		self.textures = []
		self.samplers = []
		self.channels = []
		self.texture_0 = None
		self.texture_1 = None
		self.pipeline = None

#
# Shadertoy
#
class Shadertoy:
	
	def load(self, device, window, name):
		
		# clear passes
		self.passes = []
		
		# load shader
		json = Json()
		if not json.load(path + name): return 1
		shader = json.getChild('Shader')
		info = shader.getChild('info')
		
		shader_name = ' (' + info.getData('name') + ')'
		
		Log.printf(Log.Message, '%s (%s)\n', info.getData('name'), info.getData('username'))
		Log.printf(Log.Message, '%s\n', info.getData('description'))
		Log.printf(Log.Message, 'https://shadertoy.com/view/%s\n', info.getData('id'))
		
		# get renderpasses
		renderpasses = shader.getChild('renderpass')
		if renderpasses.getNumChildren() == 0: return 1
		
		# common shader
		common_shader = ''
		for child in renderpasses.getChildren():
			code = child.getData('code')
			type = child.getData('type')
			if type == 'common': common_shader = code + '\n'
		
		# create pipelines
		for child in renderpasses.getChildren():
			code = child.getData('code')
			type = child.getData('type')
			if type == 'common': continue
			if type == 'sound': continue
			
			renderpass = RenderPass()
			self.passes.append(renderpass)
			renderpass.type = type
			
			# pass texture types
			input_types = ['2D'] * NumChannels
			
			# pass inputs
			inputs = child.getChild('inputs')
			if inputs.getNumChildren():
				for i, input in enumerate(inputs.getChildren()):
					input_src = input.getData('src')
					input_type = input.getData('ctype')
					channel = input.getData('channel', i)
					texture = None
					sampler = None
					
					# media input
					if input_src.startswith('/media'):
						source = Source()
						if source.open(path + input_src):
							
							# load image
							image = Image()
							if input_type == 'cubemap':
								face_image = Image()
								if face_image.load(source):
									image.createCube(face_image.getFormat(), face_image.getWidth())
									image.copy(face_image, Slice(Face(0)))
									name = String(input_src)
									for k in range(1, 6):
										if face_image.load('{0}{1}_{2}.{3}'.format(path, name.extension(None), k, name.extension())):
											image.copy(face_image, Slice(Face(k)))
							elif input_type == 'volume' and '.bin' in input_src:
								source.readu32()
								width = source.readu32()
								height = source.readu32()
								depth = source.readu32()
								components = source.readu32()
								if components == 1: image.create3D(FormatRu8n, width, height, depth)
								if components == 4: image.create3D(FormatRGBAu8n, width, height, depth)
								if image: source.read(image.getData(), image.getDataSize())
							else:
								image.load(source)
								
							# create sampler
							input_sampler = input.getChild('sampler')
							if input_sampler.getNumChildren():
								sampler_filter = Sampler.FilterLinear
								sampler_wrap = Sampler.WrapModeRepeat
								if input_sampler.getData('vflip', 'false') == 'true' and image.isLoaded(): image.flipY()
								if input_sampler.getData('wrap') == 'clamp': sampler_wrap = Sampler.WrapModeClamp
								if input_sampler.getData('filter') == 'point': sampler_filter = Sampler.FilterPoint
								if input_sampler.getData('filter') == 'mipmap': sampler_filter = Sampler.FilterTrilinear
								if sampler_filter == Sampler.FilterTrilinear: image = image.getMipmapped()
								sampler = device.createSampler(sampler_filter, sampler_wrap)
								
							# create texture
							if image and image.isLoaded():
								texture_flags = Texture.DefaultFlags
								if image.hasMipmaps(): texture_flags |= Texture.FlagMipmaps
								texture = device.createTexture(image, texture_flags)
								input_types[channel] = image.getTypeName()
					
					renderpass.inputs.append(input.getData('id', 0))
					renderpass.textures.append(texture)
					renderpass.samplers.append(sampler)
					renderpass.channels.append(channel)
			
			# pass output
			outputs = child.getChild('outputs')
			for j, output in enumerate(outputs.getChildren()):
				renderpass.outputs.append(output.getData('id', 0))
			
			# flip target
			flipped = False
			if renderpass.type == 'image':
				flipped = device.getPlatform() in [ PlatformVK, PlatformMTL, PlatformD3D11, PlatformD3D12 ]
			
			# vertex shader
			vertex_shader = '''#version 420 core
void main() {
	float x = (gl_VertexIndex == 0) ? 3.0f : -1.0f;
	float y = (gl_VertexIndex == 2) ? 3.0f : -1.0f;
	gl_Position = vec4(x, y, 0.0f, 1.0f);
}
'''
			
			# fragment shader
			fragment_shader = '''#version 420 core
#pragma nounused
#pragma noreserved
layout(std140, binding = 0) uniform Parameters {
	vec3 iChannelResolution[4];
	vec4 iChannelTime;
	vec3 iResolution;
	vec4 iMouse;
	float iTime;
	float iTimeDelta;
	float iDate;
	int iFrame;
};
layout(location = 0) out vec4 out_color;
'''
			for i in range(4): fragment_shader += '''\
layout(binding = {0}, set = 2) uniform sampler iSampler{0};
layout(binding = {0}, set = 1) uniform texture{1} iTexture{0};
#define iChannel{0} sampler{1}(iTexture{0}, iSampler{0})\n'''.format(i, input_types[i])
			
			fragment_shader += common_shader
			fragment_shader += code
			
			fragment_shader += '''
void main() {
	vec4 color = vec4(0.0f);
	vec2 texcoord = gl_FragCoord.xy;
'''
			if flipped: fragment_shader += '\ttexcoord.y = iResolution.y - texcoord.y;\n'
			fragment_shader += '''\
	mainImage(color, texcoord);
	out_color = color;
}
'''
			
			# create pipeline
			pipeline = device.createPipeline()
			pipeline.setTextureMasks(0, NumChannels, Shader.MaskFragment)
			pipeline.setSamplerMasks(0, NumChannels, Shader.MaskFragment)
			pipeline.setUniformMask(0, Shader.MaskFragment)
			if renderpass.type == 'buffer':
				pipeline.setColorFormat(FormatRGBAf32)
			elif renderpass.type == 'image':
				pipeline.setColorFormat(window.getColorFormat())
				pipeline.setDepthFormat(window.getDepthFormat())
			pipeline.setDepthMask(Pipeline.DepthMaskNone)
			pipeline.setDepthFunc(Pipeline.DepthFuncAlways)
			if not pipeline.createShaderGLSL(Shader.TypeVertex, vertex_shader): return 1
			if not pipeline.createShaderGLSL(Shader.TypeFragment, fragment_shader): return 1
			if not pipeline.create(): return 1
			renderpass.pipeline = pipeline

#
# main
#
def main(argv):
	
	# create app
	app = App(sys.argv)
	if not app.create(): return 1
	
	# create window
	window = Window(app.getPlatform(), app.getDevice())
	if not window: return 1
	
	window.setSize(app.getWidth(), app.getHeight())
	window.setCloseClickedCallback(lambda: window.stop())
	
	num_screenshots = 0
	def clicked_callback(key, code):
		nonlocal num_screenshots
		if key == Window.KeyEsc: window.stop()
		if key == Window.KeyF12:
			image = Image()
			if window.grab(image) and image.save('screenshot_{0}.png'.format(num_screenshots)):
				Log.printf(Log.Message, 'Screenshot %u\n', num_screenshots)
				num_screenshots += 1
	
	window.setKeyboardPressedCallback(clicked_callback)
	
	title = window.getPlatformName() + ' Tellusim::Shadertoy Python'
	if not window.create(title) or not window.setHidden(False): return 1
	
	# create device
	device = Device(window)
	if not device: return 1
	
	# default sampler
	default_sampler = device.createSampler(Sampler.FilterLinear, Sampler.WrapModeRepeat)
	if not default_sampler: return 1
	
	# default image
	default_image = Image()
	default_image.create2D(FormatRGBAu8n, 32, 32)
	default_texture = device.createTexture(default_image)
	if not default_texture: return 1
	
	# create targets
	buffer_target = device.createTarget()
	window_target = device.createTarget(window)
	
	# load shader
	index = 0
	old_index = -1
	shader = Shadertoy()
	
	# FPS counter
	fps_time = Time.seconds()
	fps_counter = 0
	
	# parameters
	mouse_position = Vector4f()
	frame_counter = 0
	old_time = 0.0
	
	# main loop
	def main_loop():
		nonlocal fps_counter
		nonlocal fps_time
		nonlocal mouse_position
		nonlocal frame_counter
		nonlocal old_time
		nonlocal index
		nonlocal old_index
		
		Window.update()
		
		if not window.render(): return False
		
		if window.getKeyboardKey(ord('1'), True): index -= 1
		if window.getKeyboardKey(ord('2'), True): index += 1
		if window.getKeyboardKey(ord('3'), True): index = index * 48271 + 23
		index = index % len(names)
		if old_index != index:
			window.finish()
			shader.load(device, window, names[index])
			old_index = index
		
		# current time
		fps_counter += 1
		time = Time.seconds()
		if time - fps_time > 1.0:
			window.setTitle('{0} {1:.1f} FPS'.format(title, fps_counter / (time - fps_time)))
			fps_time = time
			fps_counter = 0
		
		# mouse position
		if window.getMouseButtons():
			mouse_position.x = window.getMouseX()
			mouse_position.y = window.getMouseY()
			mouse_position.zw = mouse_position.xy
		else:
			mouse_position.z = 0.0
			mouse_position.w = 0.0
		
		# shader parameters
		width = window.getWidth()
		height = window.getHeight()
		parameters = bytearray()
		for i in range(NumChannels):
			parameters += Vector4f(width, height, 1.0, 0.0)
		parameters += Vector4f(time)
		parameters += Vector4f(width, height, 1.0, 0.0)
		parameters += mouse_position
		parameters += Vector2f(time)
		parameters += Scalari(frame_counter)
		parameters += Scalarf(time - old_time)
		old_time = time
		
		# resize textures
		for renderpass in shader.passes:
			if not renderpass.texture_0 or renderpass.texture_0.getWidth() != width or renderpass.texture_0.getHeight() != height:
				if renderpass.texture_0: device.releaseTexture(renderpass.texture_0)
				if renderpass.texture_1: device.releaseTexture(renderpass.texture_1)
				renderpass.texture_0 = device.createTexture2D(FormatRGBAf32, width, height, flags = Texture.FlagTarget)
				renderpass.texture_1 = device.createTexture2D(FormatRGBAf32, width, height, flags = Texture.FlagTarget)
				device.clearTexture(renderpass.texture_0, 0)
				device.clearTexture(renderpass.texture_1, 0)
		
		# render passes
		for renderpass in shader.passes:
			if not renderpass.pipeline: continue
			
			target = None
			if renderpass.type == 'image':
				target = window_target
			elif renderpass.type == 'buffer':
				buffer_target.setColorTexture(renderpass.texture_1)
				target = buffer_target
			if not target: continue
			
			# assign textures
			textures = [None] * NumChannels
			samplers = [None] * NumChannels
			for i, input in enumerate(renderpass.inputs):
				textures[renderpass.channels[i]] = renderpass.textures[i]
				samplers[renderpass.channels[i]] = renderpass.samplers[i]
				for output in shader.passes:
					if not output.outputs or output.outputs[0] != input: continue
					textures[renderpass.channels[i]] = output.texture_0
					device.flushTexture(output.texture_0)
					break
			
			# render texture
			if target.begin():
				command = device.createCommand(target)
				command.setPipeline(renderpass.pipeline)
				for i in range(NumChannels):
					if not textures[i]: textures[i] = default_texture
					if not samplers[i]: samplers[i] = default_sampler
					command.setTexture(i, textures[i])
					command.setSampler(i, samplers[i])
				command.setUniform(0, parameters)
				command.drawArrays(3)
				command = None
				target.end()
			
			# swap textures
			if renderpass.type == 'buffer':
				renderpass.texture_0, renderpass.texture_1 = renderpass.texture_1, renderpass.texture_0
		
		if not window.present(): return False
		
		device.check()
		
		return True
	
	window.run(main_loop)
	
	# finish context
	window.finish()
	
	return 0

#
# entry point
#
if __name__ == '__main__':
	try:
		exit(main(sys.argv))
	except Exception as error:
		print('\n' + str(error))
		exit(1)
