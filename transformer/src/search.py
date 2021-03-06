#coding:utf-8
import tensorflow as tf
import numpy as np


def make_mask_by_value(x):
	'''
	:param x: tensor with dtype is tf.int32
	:return:	[1,1, ..., 1, 0,0, ... , 0]
	'''
	zeros = tf.zeros_like(tensor=x, dtype=tf.int32)
	ones = tf.ones_like(tensor=x, dtype=tf.int32)
	x_mask = tf.where(condition=tf.equal(x=x, y=zeros), x=zeros, y=ones)
	return x_mask


def beam_search(batch_size, beam_width, vocab_size, max_len, hidden_size, sos_id, eos_id, inst):
	
	# encode 端
	# batch_size x seq_len
	x_placeholder = tf.placeholder(dtype=tf.int32, shape=[None, None], name='x')
	x_mask = make_mask_by_value(x=x_placeholder)
	# batch_size x seq_len x hidden_size
	memory = inst.encode(x_input=x_placeholder, x_mask=x_mask)
	y_inputs = tf.constant(value=np.ones(shape=[batch_size, 1], dtype='int32')*sos_id, dtype=tf.int32)
	# batch_size x vocab_size
	_, scores = inst.decode(y_input=y_inputs, y_mask=make_mask_by_value(y_inputs), memory=memory, memory_mask=x_mask)
	# batch_size x beam_width
	vals, idxs = tf.nn.top_k(input=scores[0], k=beam_width)
	
	# batch_size x beam_width*seq_len x hidden_size
	memorys = tf.tile(input=memory, multiples=[1, beam_width, 1])
	# batch_size*beam_width x seq_len x hidden_size
	memorys = tf.reshape(tensor=memorys, shape=[batch_size*beam_width, -1, hidden_size])
	# batch_size x beam_width*seq_len
	memorys_mask = tf.tile(input=x_mask, multiples=[1, beam_width])
	# batch_size*beam_width x seq_len
	memorys_mask = tf.reshape(tensor=memorys_mask, shape=[batch_size*beam_width, -1])
	# batch_size*beam_width x 1
	sos_ids = tf.constant(value=np.ones(shape=[batch_size*beam_width, 1], dtype='int32') * sos_id, dtype=tf.int32)
	# batch_size*beam_width x 2
	y_inputs = tf.concat(values=[sos_ids, tf.reshape(tensor=idxs, shape=[batch_size*beam_width, 1])], axis=-1)
	y_scores = tf.reshape(tensor=tf.log(x=vals), shape=[batch_size*beam_width, 1])
	
	# batch_size*beam_width x vocab_size
	next_ids = tf.convert_to_tensor(value=[[ii for ii in range(vocab_size)] for i in range(batch_size*beam_width)],
	                                dtype=tf.int32)
	# batch_size*beam_width x vocab x 1
	next_ids = tf.reshape(tensor=next_ids, shape=[batch_size*beam_width, vocab_size, 1])
	
	def cond_fn(i, y_inputs, y_scores):
		"""
		:param i: iterator
		:param y_inputs: beam_width*batch_size x i
		:param y_scores: beam_width*batch_size x 1
		"""
		cond1 = tf.less(i, max_len)
		tmp = tf.reduce_prod(tf.cast(x=tf.equal(x=y_inputs[:, -1], y=eos_id), dtype=tf.int32))
		cond2 = tf.equal(0, tmp)
		return tf.logical_and(x=cond1, y=cond2)
	
	def body_fn(i, y_inputs_ori, y_scores):
		"""
		:param i: iterator
		:param y_inputs: batch_size*beam_width x i
		:param y_scores: batch_size*beam_width x 1
		"""
		def padding_zeros(input, i, max_len):
		
			output = tf.pad(tensor=input, paddings=[[0, 0],[0, max_len - i - 1]])
			return output
		
		#batch_size*beam_width x max_len x vocab_size
		y_inputs_ = padding_zeros(input=y_inputs_ori, i=i, max_len=max_len)
		_, scores = inst.decode(y_input=y_inputs_, y_mask=make_mask_by_value(y_inputs_),
		                        memory=memorys, memory_mask=memorys_mask)
		
		next_scores = scores[:, i, :] # batch_size*beam_width x vocab_size
		y_scores_tmp = y_scores
		# batch_size*beam_width x vocab_size
		y_scores_tmp = y_scores_tmp + tf.log(x=next_scores) # y_scores_tmp will broadcast
		y_scores_tmp = tf.reshape(tensor=y_scores_tmp, shape=[batch_size, beam_width*vocab_size])
		# batch_size*beam_width x vocab_size*i
		y_inputs_ori = tf.tile(input=y_inputs_ori, multiples=[1, vocab_size])
		#batch_size*beam_width  x i x vocab_size
		y_inputs_ori = tf.reshape(tensor=y_inputs_ori, shape=[beam_width*batch_size, vocab_size, -1])
		# batch_size*beam_width x vocab_size x i, beam_width*batch_size x vocab_size x 1 -> batch_size*beam_width x vocab_size x (i+1)
		y_inputs_ori = tf.concat(values=[y_inputs_ori, next_ids], axis=-1)
		y_inputs_ori = tf.reshape(tensor=y_inputs_ori, shape=[batch_size, beam_width*vocab_size, -1])
		vals, idxs = tf.nn.top_k(input=y_scores_tmp, k=beam_width)
		# batch_size x beam_width x (i+1)
		y_inputs = tf.batch_gather(params=y_inputs_ori, indices=idxs)
		
		return i + 1, \
		       tf.reshape(tensor=y_inputs, shape=[batch_size*beam_width, -1]), \
		       tf.reshape(tensor=vals, shape=[batch_size*beam_width, -1])
	
	i_index = tf.constant(value=1, dtype=tf.int32)
	i_index, y_inputs, y_scores = tf.while_loop(cond=cond_fn,
	              body=body_fn,
	              loop_vars=[
		              i_index,
		              y_inputs,
		              y_scores
	              ],
	              shape_invariants=[
		              tf.TensorShape(dims=[]),
		              tf.TensorShape(dims=[batch_size*beam_width, None]),
		              tf.TensorShape(dims=[batch_size * beam_width, 1])
	              ])
	
	return i_index, y_inputs, y_scores, x_placeholder


def greedy_search(batch_size, max_len, sos_id, eos_id, inst):
	
	# encode 端
	# batch_size x seq_len
	x_placeholder = tf.placeholder(dtype=tf.int32, shape=[None, None], name='x')
	x_mask = make_mask_by_value(x=x_placeholder)
	# batch_size x seq_len x hidden_size
	memory = inst.encode(x_input=x_placeholder, x_mask=x_mask)
	memory_mask = x_mask
	
	def cond_fn(i, y_inputs):
		"""
		:param i: iterator
		:param y_inputs: batch_size x i
		"""
		cond1 = tf.less(i, 100)
		tmp = tf.reduce_prod(tf.cast(x=tf.equal(x=y_inputs[:, -1], y=eos_id), dtype=tf.int32))
		cond2 = tf.equal(0, tmp)
		return tf.logical_and(x=cond1, y=cond2)
	
	def body_fn(i, y_inputs):
		"""
		:param i: iterator
		:param y_inputs: batch_size x i
		:return:
		"""
		'''
		y_input, y_mask, outputs, outputs_mask, last_states
		'''
		_, scores = inst.decode(y_input=y_inputs, y_mask=make_mask_by_value(y_inputs),
		                        memory=memory, memory_mask=memory_mask)
		next_scores = scores[:, i, :]
		# batch_size x 1
		next_ids = tf.argmax(input=next_scores, axis=-1, output_type=tf.int32)
		next_ids = tf.expand_dims(input=next_ids, axis=-1)
		# batch_size x i+1
		y_inputs = tf.concat(values=[y_inputs, next_ids], axis=-1)
		#y_inputs = tf.argmax(input=scores, axis=-1)
		#y_inputs = tf.reshape(tensor=y_inputs, shape=[batch_size, -1])
		return i + 1, y_inputs
	
	# decode 端
	i_index = tf.constant(value=0, dtype=tf.int32, name='search_index')
	y_inputs = tf.constant(value=np.ones(shape=[batch_size, 1], dtype='int32') * sos_id, dtype=tf.int32)
	
	i_index, y_inputs = tf.while_loop(
		cond=cond_fn,
		body=body_fn,
		loop_vars=[i_index, y_inputs],
		shape_invariants=[
			tf.TensorShape(dims=[]),
			tf.TensorShape(dims=[batch_size, None])
		]
	)
	
	return i_index, y_inputs, x_placeholder