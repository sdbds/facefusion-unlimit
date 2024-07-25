from argparse import ArgumentParser
from time import sleep
from typing import Any, List, Literal, Optional

import cv2
import numpy

import facefusion.jobs.job_manager
import facefusion.jobs.job_store
import facefusion.processors.core as processors
from facefusion import config, logger, process_manager, state_manager, wording
from facefusion.common_helper import create_metavar, get_first
from facefusion.content_analyser import clear_content_analyser
from facefusion.download import conditional_download, is_download_done
from facefusion.execution import create_inference_session, get_static_model_initializer, has_execution_provider
from facefusion.face_analyser import clear_face_analyser, get_average_face, get_many_faces, get_one_face
from facefusion.face_helper import paste_back, warp_face_by_face_landmark_5
from facefusion.face_masker import clear_face_occluder, clear_face_parser, create_occlusion_mask, create_region_mask, create_static_box_mask
from facefusion.face_selector import find_similar_faces, sort_and_filter_faces
from facefusion.face_store import get_reference_faces
from facefusion.filesystem import filter_image_paths, has_image, in_directory, is_file, is_image, is_video, resolve_relative_path, same_file_extension
from facefusion.processors import choices as processors_choices
from facefusion.processors.expression_restorer import clear_expression_restorer, restore_expression
from facefusion.processors.pixel_boost import explode_pixel_boost, implode_pixel_boost
from facefusion.processors.typing import FaceSwapperInputs
from facefusion.program_helper import find_argument_group, suggest_face_swapper_pixel_boost_choices
from facefusion.thread_helper import conditional_thread_semaphore, thread_lock
from facefusion.typing import Args, Embedding, Face, ModelSet, OptionsWithModel, ProcessMode, QueuePayload, UpdateProgress, VisionFrame
from facefusion.vision import read_image, read_static_image, read_static_images, unpack_resolution, write_image

PROCESSOR = None
NAME = __name__.upper()
MODELS : ModelSet =\
{
	'blendswap_256':
	{
		'type': 'blendswap',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/blendswap_256.onnx',
		'path': resolve_relative_path('../.assets/models/blendswap_256.onnx'),
		'template': 'ffhq_512',
		'size': (256, 256),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	},
	'ghost_256_unet_1':
	{
		'type': 'ghost',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/ghost_256_unet_1.onnx',
		'path': resolve_relative_path('../.assets/models/ghost_256_unet_1.onnx'),
		'template': 'arcface_112_v1',
		'size': (256, 256),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	},
	'ghost_256_unet_2':
	{
		'type': 'ghost',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/ghost_256_unet_2.onnx',
		'path': resolve_relative_path('../.assets/models/ghost_256_unet_2.onnx'),
		'template': 'arcface_112_v1',
		'size': (256, 256),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	},
	'ghost_256_unet_3':
	{
		'type': 'ghost',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/ghost_256_unet_3.onnx',
		'path': resolve_relative_path('../.assets/models/ghost_256_unet_3.onnx'),
		'template': 'arcface_112_v1',
		'size': (256, 256),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	},
	'inswapper_128':
	{
		'type': 'inswapper',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/inswapper_128.onnx',
		'path': resolve_relative_path('../.assets/models/inswapper_128.onnx'),
		'template': 'arcface_128_v2',
		'size': (128, 128),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	},
	'inswapper_128_fp16':
	{
		'type': 'inswapper',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/inswapper_128_fp16.onnx',
		'path': resolve_relative_path('../.assets/models/inswapper_128_fp16.onnx'),
		'template': 'arcface_128_v2',
		'size': (128, 128),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	},
	'simswap_256':
	{
		'type': 'simswap',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/simswap_256.onnx',
		'path': resolve_relative_path('../.assets/models/simswap_256.onnx'),
		'template': 'arcface_112_v1',
		'size': (256, 256),
		'mean': [ 0.485, 0.456, 0.406 ],
		'standard_deviation': [ 0.229, 0.224, 0.225 ]
	},
	'simswap_512_unofficial':
	{
		'type': 'simswap',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/simswap_512_unofficial.onnx',
		'path': resolve_relative_path('../.assets/models/simswap_512_unofficial.onnx'),
		'template': 'arcface_112_v1',
		'size': (512, 512),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	},
	'uniface_256':
	{
		'type': 'uniface',
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/uniface_256.onnx',
		'path': resolve_relative_path('../.assets/models/uniface_256.onnx'),
		'template': 'ffhq_512',
		'size': (256, 256),
		'mean': [ 0.0, 0.0, 0.0 ],
		'standard_deviation': [ 1.0, 1.0, 1.0 ]
	}
}
OPTIONS : Optional[OptionsWithModel] = None


def get_processor() -> Any:
	global PROCESSOR

	with thread_lock():
		while process_manager.is_checking():
			sleep(0.5)
		if PROCESSOR is None:
			model_path = get_options('model').get('path')
			PROCESSOR = create_inference_session(model_path, state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
	return PROCESSOR


def clear_processor() -> None:
	global PROCESSOR

	PROCESSOR = None


def get_options(key : Literal['model']) -> Any:
	global OPTIONS

	if OPTIONS is None:
		face_swapper_model = 'inswapper_128' if has_execution_provider('coreml') or has_execution_provider('openvino') and state_manager.get_item('face_swapper_model') == 'inswapper_128_fp16' else state_manager.get_item('face_swapper_model')
		OPTIONS =\
		{
			'model': MODELS[face_swapper_model]
		}
	return OPTIONS.get(key)


def set_options(key : Literal['model'], value : Any) -> None:
	global OPTIONS

	OPTIONS[key] = value


def register_args(program : ArgumentParser) -> None:
	group_processors = find_argument_group(program, 'processors')
	if group_processors:
		group_processors.add_argument('--face-swapper-model', help = wording.get('help.face_swapper_model'), default = config.get_str_value('processors.face_swapper_model', 'inswapper_128_fp16'), choices = processors_choices.face_swapper_set.keys())
		face_swapper_pixel_boost_choices = suggest_face_swapper_pixel_boost_choices(program)
		group_processors.add_argument('--face-swapper-pixel-boost', help = wording.get('help.face_swapper_pixel_boost'), default = config.get_str_value('processors.face_swapper_pixel_boost', get_first(face_swapper_pixel_boost_choices)), choices = face_swapper_pixel_boost_choices)
		group_processors.add_argument('--face-swapper-expression-restorer', help = wording.get('help.face_swapper_expression_restorer'), type = float, default = config.get_int_value('processors.face_swapper_expression_restorer', '0'), choices = processors_choices.face_swapper_expression_restorer_range, metavar = create_metavar(processors_choices.face_swapper_expression_restorer_range))
		facefusion.jobs.job_store.register_step_keys([ 'face_swapper_model', 'face_swapper_pixel_boost', 'face_swapper_expression_restorer' ])


def apply_args(args : Args) -> None:
	state_manager.init_item('face_swapper_model', args.get('face_swapper_model'))
	state_manager.init_item('face_swapper_pixel_boost', args.get('face_swapper_pixel_boost'))
	state_manager.init_item('face_swapper_expression_restorer', args.get('face_swapper_expression_restorer'))

	if state_manager.get_item('face_swapper_model') == 'blendswap_256':
		state_manager.init_item('face_recognizer_model', 'arcface_blendswap')
	if state_manager.get_item('face_swapper_model') in [ 'ghost_256_unet_1', 'ghost_256_unet_2', 'ghost_256_unet_3' ]:
		state_manager.init_item('face_recognizer_model', 'arcface_ghost')
	if state_manager.get_item('face_swapper_model') in [ 'inswapper_128', 'inswapper_128_fp16' ]:
		state_manager.init_item('face_recognizer_model', 'arcface_inswapper')
	if state_manager.get_item('face_swapper_model') in [ 'simswap_256', 'simswap_512_unofficial' ]:
		state_manager.init_item('face_recognizer_model', 'arcface_simswap')
	if state_manager.get_item('face_swapper_model') == 'uniface_256':
		state_manager.init_item('face_recognizer_model', 'arcface_uniface')


def pre_check() -> bool:
	download_directory_path = resolve_relative_path('../.assets/models')
	model_url = get_options('model').get('url')
	model_path = get_options('model').get('path')

	if not state_manager.get_item('skip_download'):
		process_manager.check()
		conditional_download(download_directory_path, [ model_url ])
		process_manager.end()
	return is_file(model_path)


def post_check() -> bool:
	model_url = get_options('model').get('url')
	model_path = get_options('model').get('path')

	if not state_manager.get_item('skip_download') and not is_download_done(model_url, model_path):
		logger.error(wording.get('model_download_not_done') + wording.get('exclamation_mark'), NAME)
		return False
	if not is_file(model_path):
		logger.error(wording.get('model_file_not_present') + wording.get('exclamation_mark'), NAME)
		return False
	return True


def pre_process(mode : ProcessMode) -> bool:
	if not has_image(state_manager.get_item('source_paths')):
		logger.error(wording.get('choose_image_source') + wording.get('exclamation_mark'), NAME)
		return False
	source_image_paths = filter_image_paths(state_manager.get_item('source_paths'))
	source_frames = read_static_images(source_image_paths)
	source_faces = get_many_faces(source_frames)
	if not get_one_face(source_faces):
		logger.error(wording.get('no_source_face_detected') + wording.get('exclamation_mark'), NAME)
		return False
	if mode in [ 'output', 'preview' ] and not is_image(state_manager.get_item('target_path')) and not is_video(state_manager.get_item('target_path')):
		logger.error(wording.get('choose_image_or_video_target') + wording.get('exclamation_mark'), NAME)
		return False
	if mode == 'output' and not in_directory(state_manager.get_item('output_path')):
		logger.error(wording.get('specify_image_or_video_output') + wording.get('exclamation_mark'), NAME)
		return False
	if mode == 'output' and not same_file_extension([ state_manager.get_item('target_path'), state_manager.get_item('output_path') ]):
		logger.error(wording.get('match_target_and_output_extension') + wording.get('exclamation_mark'), NAME)
		return False
	return True


def post_process() -> None:
	read_static_image.cache_clear()
	get_static_model_initializer.cache_clear()
	if state_manager.get_item('video_memory_strategy') in [ 'strict', 'moderate' ]:
		clear_processor()
	if state_manager.get_item('video_memory_strategy') == 'strict':
		clear_face_analyser()
		clear_content_analyser()
		clear_face_occluder()
		clear_face_parser()
		clear_expression_restorer()


def swap_face(source_face : Face, target_face : Face, temp_vision_frame : VisionFrame) -> VisionFrame:
	model_template = get_options('model').get('template')
	model_size = get_options('model').get('size')
	pixel_boost_size = unpack_resolution(state_manager.get_item('face_swapper_pixel_boost'))
	pixel_boost_total = pixel_boost_size[0] // model_size[0]
	crop_vision_frame, affine_matrix = warp_face_by_face_landmark_5(temp_vision_frame, target_face.landmark_set.get('5/68'), model_template, pixel_boost_size)
	source_vision_frame = crop_vision_frame.copy()
	crop_masks = []
	temp_vision_frames = []

	if 'box' in state_manager.get_item('face_mask_types'):
		box_mask = create_static_box_mask(crop_vision_frame.shape[:2][::-1], state_manager.get_item('face_mask_blur'), state_manager.get_item('face_mask_padding'))
		crop_masks.append(box_mask)
	if 'occlusion' in state_manager.get_item('face_mask_types'):
		occlusion_mask = create_occlusion_mask(crop_vision_frame)
		crop_masks.append(occlusion_mask)
	pixel_boost_vision_frames = implode_pixel_boost(crop_vision_frame, pixel_boost_total, model_size)
	for pixel_boost_vision_frame in pixel_boost_vision_frames:
		pixel_boost_vision_frame = prepare_crop_frame(pixel_boost_vision_frame)
		pixel_boost_vision_frame = apply_swap(source_face, pixel_boost_vision_frame)
		pixel_boost_vision_frame = normalize_crop_frame(pixel_boost_vision_frame)
		temp_vision_frames.append(pixel_boost_vision_frame)
	crop_vision_frame = explode_pixel_boost(temp_vision_frames, pixel_boost_total, model_size, pixel_boost_size)
	if 'region' in state_manager.get_item('face_mask_types'):
		region_mask = create_region_mask(crop_vision_frame, state_manager.get_item('face_mask_regions'))
		crop_masks.append(region_mask)
	crop_mask = numpy.minimum.reduce(crop_masks).clip(0, 1)
	if state_manager.get_item('face_swapper_expression_restorer') > 0:
		crop_vision_frame, matrix_scale = restore_expression(source_vision_frame, crop_vision_frame, state_manager.get_item('face_swapper_expression_restorer'))
		crop_mask = cv2.resize(crop_mask, crop_vision_frame.shape[:2][::-1])
		affine_matrix *= matrix_scale
	temp_vision_frame = paste_back(temp_vision_frame, crop_vision_frame, crop_mask, affine_matrix)
	return temp_vision_frame


def apply_swap(source_face : Face, crop_vision_frame : VisionFrame) -> VisionFrame:
	processor = get_processor()
	model_type = get_options('model').get('type')
	processor_inputs = {}

	for processor_input in processor.get_inputs():
		if processor_input.name == 'source':
			if model_type == 'blendswap' or model_type == 'uniface':
				processor_inputs[processor_input.name] = prepare_source_frame(source_face)
			else:
				processor_inputs[processor_input.name] = prepare_source_embedding(source_face)
		if processor_input.name == 'target':
			processor_inputs[processor_input.name] = crop_vision_frame

	with conditional_thread_semaphore():
		crop_vision_frame = processor.run(None, processor_inputs)[0][0]

	return crop_vision_frame


def prepare_source_frame(source_face : Face) -> VisionFrame:
	model_type = get_options('model').get('type')
	source_vision_frame = read_static_image(get_first(state_manager.get_item('source_paths')))

	if model_type == 'blendswap':
		source_vision_frame, _ = warp_face_by_face_landmark_5(source_vision_frame, source_face.landmark_set.get('5/68'), 'arcface_112_v2', (112, 112))
	if model_type == 'uniface':
		source_vision_frame, _ = warp_face_by_face_landmark_5(source_vision_frame, source_face.landmark_set.get('5/68'), 'ffhq_512', (256, 256))
	source_vision_frame = source_vision_frame[:, :, ::-1] / 255.0
	source_vision_frame = source_vision_frame.transpose(2, 0, 1)
	source_vision_frame = numpy.expand_dims(source_vision_frame, axis = 0).astype(numpy.float32)
	return source_vision_frame


def prepare_source_embedding(source_face : Face) -> Embedding:
	model_type = get_options('model').get('type')
	model_path = get_options('model').get('path')

	if model_type == 'ghost':
		source_embedding = source_face.embedding.reshape(1, -1)
	elif model_type == 'inswapper':
		model_initializer = get_static_model_initializer(model_path)
		source_embedding = source_face.embedding.reshape((1, -1))
		source_embedding = numpy.dot(source_embedding, model_initializer) / numpy.linalg.norm(source_embedding)
	else:
		source_embedding = source_face.normed_embedding.reshape(1, -1)
	return source_embedding


def prepare_crop_frame(crop_vision_frame : VisionFrame) -> VisionFrame:
	model_type = get_options('model').get('type')
	model_mean = get_options('model').get('mean')
	model_standard_deviation = get_options('model').get('standard_deviation')

	if model_type == 'ghost':
		crop_vision_frame = crop_vision_frame[:, :, ::-1] / 127.5 - 1
	else:
		crop_vision_frame = crop_vision_frame[:, :, ::-1] / 255.0
	crop_vision_frame = (crop_vision_frame - model_mean) / model_standard_deviation
	crop_vision_frame = crop_vision_frame.transpose(2, 0, 1)
	crop_vision_frame = numpy.expand_dims(crop_vision_frame, axis = 0).astype(numpy.float32)
	return crop_vision_frame


def normalize_crop_frame(crop_vision_frame : VisionFrame) -> VisionFrame:
	model_template = get_options('model').get('type')
	crop_vision_frame = crop_vision_frame.transpose(1, 2, 0)

	if model_template == 'ghost':
		crop_vision_frame = (crop_vision_frame * 127.5 + 127.5).round()
	else:
		crop_vision_frame = (crop_vision_frame * 255.0).round()
	crop_vision_frame = crop_vision_frame[:, :, ::-1]
	return crop_vision_frame


def get_reference_frame(source_face : Face, target_face : Face, temp_vision_frame : VisionFrame) -> VisionFrame:
	return swap_face(source_face, target_face, temp_vision_frame)


def process_frame(inputs : FaceSwapperInputs) -> VisionFrame:
	reference_faces = inputs.get('reference_faces')
	source_face = inputs.get('source_face')
	target_vision_frame = inputs.get('target_vision_frame')
	many_faces = sort_and_filter_faces(get_many_faces([ target_vision_frame ]))

	if state_manager.get_item('face_selector_mode') == 'many':
		if many_faces:
			for target_face in many_faces:
				target_vision_frame = swap_face(source_face, target_face, target_vision_frame)
	if state_manager.get_item('face_selector_mode') == 'one':
		target_face = get_one_face(many_faces)
		if target_face:
			target_vision_frame = swap_face(source_face, target_face, target_vision_frame)
	if state_manager.get_item('face_selector_mode') == 'reference':
		similar_faces = find_similar_faces(many_faces, reference_faces, state_manager.get_item('reference_face_distance'))
		if similar_faces:
			for similar_face in similar_faces:
				target_vision_frame = swap_face(source_face, similar_face, target_vision_frame)
	return target_vision_frame


def process_frames(source_paths : List[str], queue_payloads : List[QueuePayload], update_progress : UpdateProgress) -> None:
	reference_faces = get_reference_faces() if 'reference' in state_manager.get_item('face_selector_mode') else None
	source_frames = read_static_images(source_paths)
	source_faces = get_many_faces(source_frames)
	source_face = get_average_face(source_faces)

	for queue_payload in process_manager.manage(queue_payloads):
		target_vision_path = queue_payload['frame_path']
		target_vision_frame = read_image(target_vision_path)
		output_vision_frame = process_frame(
		{
			'reference_faces': reference_faces,
			'source_face': source_face,
			'target_vision_frame': target_vision_frame
		})
		write_image(target_vision_path, output_vision_frame)
		update_progress(1)


def process_image(source_paths : List[str], target_path : str, output_path : str) -> None:
	reference_faces = get_reference_faces() if 'reference' in state_manager.get_item('face_selector_mode') else None
	source_frames = read_static_images(source_paths)
	source_faces = get_many_faces(source_frames)
	source_face = get_average_face(source_faces)
	target_vision_frame = read_static_image(target_path)
	output_vision_frame = process_frame(
	{
		'reference_faces': reference_faces,
		'source_face': source_face,
		'target_vision_frame': target_vision_frame
	})
	write_image(output_path, output_vision_frame)


def process_video(source_paths : List[str], temp_frame_paths : List[str]) -> None:
	processors.multi_process_frames(source_paths, temp_frame_paths, process_frames)