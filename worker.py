# coding: utf-8
from subprocess import Popen
from time import sleep
from zlib import compress, decompress
from pickle import dumps, loads, HIGHEST_PROTOCOL
from struct import pack, unpack
import logging
import numpy as np
import redis
import pickle
import sys
import os
import socket
import timeit


chunk_data = sys.argv[1]
worker_id = sys.argv[2]
cur_iter = int(sys.argv[3])
embedding_dim = int(sys.argv[4])
redis_ip_address = sys.argv[5]
root_dir = sys.argv[6]
socket_port = int(sys.argv[7])
debugging = sys.argv[8]
precision = int(sys.argv[9])
precision_string = 'f' if precision == 0 else 'e'
precision_byte = 4 if precision == 0 else 2

if debugging == 'yes':
    logging.basicConfig(filename='%s/%s_%d.log' % (root_dir,
                                                   worker_id, cur_iter), filemode='w', level=logging.WARNING)
    logger = logging.getLogger()
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(handler)

    def printt(str):

        print(str)
        logger.warning(str + '\n')

    def handle_exception(exc_type, exc_value, exc_traceback):

        if issubclass(exc_type, KeyboardInterrupt):

            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.error("exception", exc_info=(
            exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

elif debugging == 'no':

    printt = print


def sockRecv(sock, length):

    data = b''

    while len(data) < length:

        buff = sock.recv(length - len(data))

        if not buff:

            return None

        data = data + buff

    return data


preprocess_folder_dir = "%s/preprocess/" % root_dir
train_code_dir = "%s/MultiChannelEmbedding/Embedding.out" % root_dir
temp_folder_dir = "%s/tmp" % root_dir

workerStart = timeit.default_timer()
# redis에서 embedding vector들 받아오기
r = redis.StrictRedis(host=redis_ip_address, port=6379, db=0)
entities = np.array(loads(decompress(r.get('entities'))))
relations = np.array(loads(decompress(r.get('relations'))))
entity_ids = np.array([int(i) for i in r.mget(entities)], dtype=np.int32)
relation_ids = np.array([int(i) for i in r.mget(relations)], dtype=np.int32)
entities_initialized = r.mget([entity + '_v' for entity in entities])
relations_initialized = r.mget([relation + '_v' for relation in relations])

entity_id = {e: i for e, i in zip(entities, entity_ids)}
relation_id = {r: i for e, i in zip(relations, relation_ids)}

entities_initialized = np.array([loads(decompress(v))
                        for v in entities_initialized], dtype=np.float32)
relations_initialized = np.array([loads(decompress(v))
                         for v in relations_initialized], dtype=np.float32)

redisTime = timeit.default_timer() - workerStart
# printt('worker > redis server connection time : %f' % (redisTime))

# embedding.cpp 와 socket 통신
# worker 가 실행될 때 전달받은 ip 와 port 로 접속
# Embedding.cpp 가 server, 프로세느는 master.py 가 생성
# worker.py 가 client
# 첫 iteration 에서눈 Embedding.cpp 의 실행, 소켓 생성을 기다림

trial = 0
while True:

    try:

        embedding_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        break

    except Exception as e:

        sleep(0.5)
        trial = trial + 1
        printt('[error] worker > exception occured in worker <-> embedding')
        printt('[error] worker > ' + str(e))

    if trial == 5:

        printt(f'[error] worker > iteration {cur_iter} failed - {worker_id}')
        printt('[error] worker > return -1')
        sys.exit(-1)

trial = 0
while True:

    try:

        embedding_sock.connect(('127.0.0.1', socket_port))
        break

    except Exception as e:

        sleep(0.5)
        trial = trial + 1
        printt('[error] worker > exception occured in worker <-> embedding')
        printt('[error] worker > ' + str(e))

    if trial == 5:

        printt(f'[error] worker > iteration {cur_iter} failed - {worker_id}')
        printt('[error] worker > return -1')
        sys.exit(-1)

#printt('worker > port number of ' + worker_id + ' = ' + socket_port)
# printt('worker > socket connected (worker <-> embedding)')

# 파일로 로그를 저장하기 위한 부분
# fsLog = open(os.path.join(root_dir, 'logs/worker_log_' + worker_id + '_iter_' + cur_iter + '.txt'), 'w')
# fsLog.write('line 143 start\n')

# DataModel 생성자 -> GeometricModel load 메소드 -> GeometricModel save 메소드 순서로 통신
try:

    checksum = 0
    timeNow = timeit.default_timer()

    if cur_iter % 2 == 0:
        # entity 전송 - DataModel 생성자
        chunk_anchor, chunk_entity = chunk_data.split('\n')
        chunk_anchor = chunk_anchor.split(' ')
        chunk_anchor = [int(e) for e in chunk_anchor]
        chunk_entity = chunk_entity.split(' ')
        chunk_entity = [int(e) for e in chunk_entity]

        if len(chunk_anchor) == 1 and chunk_anchor[0] == '':

            chunk_anchor = []

        while checksum != 1:

            # 원소 하나씩 전송
            #embedding_sock.send(pack('!i', len(chunk_anchor)))
            #
            # for iter_anchor in chunk_anchor:
            #
            #    embedding_sock.send(pack('!i', int(iter_anchor)))
            #
            #embedding_sock.send(pack('!i', len(chunk_entity)))
            #
            # for iter_entity in chunk_entity:
            #
            #    embedding_sock.send(pack('!i', int(iter_entity)))

            # 원소 한 번에 전송 - 1 단계
            #value_to_send = [int(e) for e in chunk_anchor]
            #embedding_sock.send(pack('!i', len(chunk_anchor)))
            #embedding_sock.send(pack(
            #    '!' + 'i' * len(chunk_anchor), * value_to_send))
            #
            #value_to_send = [int(e) for e in chunk_entity]
            #embedding_sock.send(pack('!i', len(chunk_entity)))
            #embedding_sock.send(pack(
            #    '!' + 'i' * len(chunk_entity), * value_to_send))

            # 원소 한 번에 전송 - 2 단계
            value_to_send = [len(chunk_anchor), len(chunk_entity), *chunk_anchor, *chunk_entity]
            embedding_sock.send(pack('!' + 'i' * (len(chunk_anchor) + len(chunk_entity) + 2), * value_to_send))

            checksum = unpack('!i', sockRecv(embedding_sock, 4))[0]

            if checksum == 1234:

                #printt('worker > phase 1 finished - ' + worker_id)
                #fsLog.write('worker > phase 1 finished - ' + worker_id + '\n')
                checksum = 1

            elif checksum == 9876:

                printt('[error] worker > retry phase 1 - ' + worker_id)
                # fsLog.write('[error] worker > retry phase 1 - ' + worker_id + '\n')
                checksum = 0

            else:

                printt('[error] worker > unknown error in phase 1 - ' + worker_id)
                printt('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id)
                printt('[error] worker > return -1')
                # fsLog.write('[error] worker > unknown error in phase 1 - ' + worker_id + '\n')
                # fsLog.write('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id + '\n')
                # fsLog.write('[error] worker > return -1\n')
                # fsLog.close()
                sys.exit(-1)

        #printt('worker > phase 1 : entity sent to DataModel finished')
        #fsLog.write('worker > phase 1 : entity sent to DataModel finished\n')

    else:
        # relation 전송 - DataModel 생성자
        timeNow = timeit.default_timer()
        sub_graphs = loads(decompress(r.get('sub_g_{}'.format(worker_id))))
        redisTime += timeit.default_timer() - timeNow
        
        while checksum != 1:

            embedding_sock.send(pack('!i', len(sub_graphs)))

            # 원소 하나씩 전송
            # for (head_id_, relation_id_, tail_id_) in sub_graphs:
            #
            #    embedding_sock.send(pack('!i', head_id_))
            #    embedding_sock.send(pack('!i', relation_id_))
            #    embedding_sock.send(pack('!i', tail_id_))

            # 원소 한 번에 전송 - 1 단계
            # for triple in sub_graphs:
                
            #     embedding_sock.send(pack('!iii', *triple))

            # 원소 한 번에 전송 - 2 단계
            value_to_send = list()
            value_to_send_extend = value_to_send.extend
            
            for triple in sub_graphs:
            
               value_to_send_extend(triple)
            
            embedding_sock.send(pack('!' + 'i' * len(value_to_send), * value_to_send))

            checksum = unpack('!i', sockRecv(embedding_sock, 4))[0]

            if checksum == 1234:

                #printt('worker > phase 1 finished - ' + worker_id)
                #fsLog.write('worker > phase 1 finished - ' + worker_id + '\n')
                checksum = 1

            elif checksum == 9876:

                printt('[error] worker > retry phase 1 - ' + worker_id)
                # fsLog.write('[error] worker > retry phase 1 - ' + worker_id + '\n')
                checksum = 0

            else:

                printt('[error] worker > unknown error in phase 1 - ' + worker_id)
                printt('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id)
                printt('[error] worker > return -1')
                # fsLog.write('[error] worker > unknown error in phase 1 - ' + worker_id + '\n')
                # fsLog.write('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id + '\n')
                # fsLog.write('[error] worker > return -1\n')
                # fsLog.close()
                sys.exit(-1)

        #printt('worker > phase 1 : relation sent to DataModel finished')
        #fsLog.write('worker > phase 1 : relation sent to DataModel finished\n')

    datamodelTime = timeit.default_timer() - timeNow
    checksum = 0
    timeNow = timeit.default_timer()

    # entity_vector 전송 - GeometricModel load
    while checksum != 1:

        # 원소를 하나씩 전송
        # for i, vector in enumerate(entities_initialized):
        #
        #    entity_name = str(entities[i])
        #    id_entity[entity_id[entity_name]] = entity_name
        #    embedding_sock.send(pack('!i', entity_id[entity_name]))
        #
        #    for v in vector:
        #
        #        embedding_sock.send(pack(precision_string, float(v)))

        # 원소를 한 번에 전송 - 1 단계
        #for i, vector in enumerate(entities_initialized):
        #
        #    entity_name = str(entities[i])
        #    id_entity[entity_id[entity_name]] = entity_name
        #    embedding_sock.send(pack('!i', entity_id[entity_name]))
        #    embedding_sock.send(pack(
        #        precision_string * len(vector), * vector.tolist()))

        # 원소를 한 번에 전송 - 2 단계
        value_to_send_vector = entities_initialized.flatten()
        embedding_sock.send(pack('!' + 'i' * len(entity_ids), * entity_ids))
        embedding_sock.send(pack(precision_string * len(value_to_send_vector), * value_to_send_vector))

        checksum = unpack('!i', sockRecv(embedding_sock, 4))[0]

        if checksum == 1234:

            #printt('worker > phase 2 (entity) finished - ' + worker_id)
            #fsLog.write('worker > phase 2 (entity) finished - ' + worker_id + '\n')
            checksum = 1

        elif checksum == 9876:

            printt('[error] worker > retry phase 2 (entity) - ' + worker_id)
            # fsLog.write('[error] worker > retry phase 2 (entity) - ' + worker_id + '\n')
            checksum = 0

        else:

            printt('[error] worker > unknown error in phase 2 (entity) - ' + worker_id)
            printt('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id)
            printt('[error] worker > return -1')
            # fsLog.write('[error] worker > unknown error in phase 2 (entity) - ' + worker_id + '\n')
            # fsLog.write('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id + '\n')
            # fsLog.write('[error] worker > return -1\n')
            # fsLog.close()
            sys.exit(-1)

    #printt('worker > phase 2.1 : entity_vector sent to GeometricModel load function')
    #fsLog.write('worker > phase 2.1 : entity_vector sent to GeometricModel load function\n')

    checksum = 0

    # relation_vector 전송 - GeometricModel load
    while checksum != 1:

        # 원소를 하나씩 전송
        # for i, relation in enumerate(relations_initialized):
        #
        #    relation_name = str(relations[i])
        #    id_relation[relation_id[relation_name]] = relation_name
        #    embedding_sock.send(pack('!i', relation_id[relation_name])) # relation id 를 int 로 전송
        #
        #    for v in relation:
        #
        #        embedding_sock.send(pack(precision_string, float(v)))

        # 원소를 한 번에 전송 - 1 단계
        #for i, relation in enumerate(relations_initialized):
        #
        #    relation_name = str(relations[i])
        #    id_relation[relation_id[relation_name]] = relation_name
        #    embedding_sock.send(pack('!i', relation_id[relation_name]))
        #    embedding_sock.send(pack(
        #        precision_string * len(relation), * relation.tolist()))

        # 원소를 한 번에 전송 - 2 단계
        value_to_send_vector = relations_initialized.flatten()
        embedding_sock.send(pack('!' + 'i' * len(relation_ids), * relation_ids))
        embedding_sock.send(pack(precision_string * len(value_to_send_vector), * value_to_send_vector))

        checksum = unpack('!i', sockRecv(embedding_sock, 4))[0]

        if checksum == 1234:

            #printt('worker > phase 2 (relation) finished - ' + worker_id)
            #fsLog.write('worker > phase 2 (relation) finished - ' + worker_id + '\n')
            checksum = 1

        elif checksum == 9876:

            printt(
                '[error] worker > retry phase 2 (relation) - worker.py - ' + worker_id)
            # fsLog.write('[error] worker > retry phase 2 (relation) - ' + worker_id + '\n')
            checksum = 0

        else:

            printt(
                '[error] worker > unknown error in phase 2 (relation) - ' + worker_id)
            printt('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id)
            printt('[error] worker > return -1')
            # fsLog.write('[error] worker > unknown error in phase 2 (relation) - ' + worker_id + '\n')
            # fsLog.write('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id + '\n')
            # fsLog.write('[error] worker > return -1\n')
            # fsLog.close()
            sys.exit(-1)

    sockLoadTime = timeit.default_timer() - timeNow
    timeNow = timeit.default_timer()

    #printt('worker > phase 2.2 : relation_vector sent to GeometricModel load function')
    #fsLog.write('worker > phase 2.2 : relation_vector sent to GeometricModel load function\n')

    del entities_initialized
    del relations_initialized
    del value_to_send_vector

    tempcount = 0

    if cur_iter % 2 == 0:

        success = 0

        while success != 1:

            try:

                embeddingTime = timeit.default_timer() - timeNow
                # 처리 결과를 받아옴 - GeometricModel save

                # 원소를 하나씩 받음
                #count_entity = unpack('!i', sockRecv(embedding_sock, 4))[0]
                #
                #for _ in range(count_entity):
                #
                #    temp_entity_vector = list()
                #
                #    entity_id_temp = unpack('!i', sockRecv(embedding_sock, 4))[0]     # entity_id 를 int 로 받음
                #
                #
                #    for _ in range(embedding_dim):
                #
                #        temp_entity = unpack(precision_string, sockRecv(embedding_sock, precision_byte))[0]
                #        temp_entity_vector.append(temp_entity)
                #
                #    entity_vectors[id_entity[entity_id_temp] + '_v'] = compress(dumps(
                #        np.array(temp_entity_vector, dtype=np.float32), protocol=HIGHEST_PROTOCOL), 9)

                # 원소를 한 번에 받음
                #count_entity = unpack('!i', sockRecv(embedding_sock, 4))[0]
                #
                #for _ in range(count_entity):
                #
                #   entity_id_temp = unpack('!i', sockRecv(embedding_sock, 4))[0]
                #   temp_entity_vector = list(unpack(precision_string * embedding_dim, sockRecv(embedding_sock, precision_byte * embedding_dim)))
                #
                #   entity_vectors[entities[entity_id_temp] + '_v'] = compress(dumps(
                #       np.array(temp_entity_vector, dtype=np.float32), protocol=HIGHEST_PROTOCOL), 9)
                
                # 원소를 한 번에 받음 (엔티티 한 번에)
                count_entity = int(unpack('!i', sockRecv(embedding_sock, 4))[0])
                entity_id_list = unpack('!' + 'i' * count_entity, sockRecv(embedding_sock, count_entity * 4))
                entity_vector_list = unpack(precision_string * count_entity * embedding_dim,
                    sockRecv(embedding_sock, precision_byte * embedding_dim * count_entity))
                entity_vector_list = np.array(entity_vector_list, dtype=np.float32).reshape(count_entity, embedding_dim)

                entity_vectors = {
                    entities[_id + '_v']: compress(dumps(entity_vector_list[_i], protocol=HIGHEST_PROTOCOL), 9)
                    for _i, _id in enumerate(entity_id_list)}

            except Exception as e:

                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

                if tempcount < 3:

                    printt('[error] worker > retry phase 3 (entity) - ' + worker_id)
                    printt('[error] worker > ' + str(e))
                    printt('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno))
                    # fsLog.write('[error] worker > retry phase 3 (entity) - ' + worker_id + '\n')
                    # fsLog.write('[error] worker > ' + str(e) + '\n')
                    # fsLog.write('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno) + '\n')

                else:

                    printt('[error] worker > failed phase 3 (entity) - ' + worker_id)
                    printt('[error] worker > ' + str(e))
                    printt('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno))
                    printt('[error] worker > return -1')
                    # fsLog.write('[error] worker > retry phase 3 (entity) - ' + worker_id + '\n')
                    # fsLog.write('[error] worker > ' + str(e) + '\n')
                    # fsLog.write('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno) + '\n')
                    # fsLog.write('[error] worker > return -1\n')
                    # fsLog.close()
                    sys.exit(-1)

                tempcount = tempcount + 1
                flag = 9876
                embedding_sock.send(pack('!i', flag))
                success = 0

            else:

                #printt('worker > phase 3 (entity) finished - ' + worker_id)
                #fsLog.write('worker > phase 3 (entity) finished - ' + worker_id + '\n')
                flag = 1234
                embedding_sock.send(pack('!i', flag))
                success = 1

        sockSaveTime = timeit.default_timer() - timeNow
        timeNow = timeit.default_timer()

        r.mset(entity_vectors)
        #printt('worker > entity_vectors updated - ' + worker_id)
        #printt('worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id)
        #fsLog.write('worker > entity_vectors updated - ' + worker_id + '\n')
        #fsLog.write('worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id + '\n')
        # fsLog.close()
        redisTime += timeit.default_timer() - timeNow

    else:

        success = 0

        while success != 1:

            try:

                relation_vectors = dict()

                embeddingTime = timeit.default_timer() - timeNow
                # 처리 결과를 받아옴 - GeometricModel save

                # 원소를 하나씩 전송
                #count_relation = unpack('!i', sockRecv(embedding_sock, 4))[0]
                #
                #for _ in range(count_relation):
                #
                #    temp_relation_vector = list()
                #
                #    relation_id_temp = unpack('!i', sockRecv(embedding_sock, 4))[0]   # relation_id 를 int 로 받음 
                #
                #    for _ in range(embedding_dim):
                #
                #        temp_relation = unpack(precision_string, sockRecv(embedding_sock, precision_byte))[0]
                #        temp_relation_vector.append(temp_relation)
                #
                #    relation_vectors[id_relation[relation_id_temp] + '_v'] = compress(dumps(
                #        np.array(temp_relation_vector, dtype=np.float32), protocol=HIGHEST_PROTOCOL), 9)

                # 원소를 한 번에 받음
                #count_relation = unpack('!i', sockRecv(embedding_sock, 4))[0]
                #
                #for _ in range(count_relation):
                #
                #   relation_id_temp = unpack('!i', sockRecv(embedding_sock, 4))[0]
                #   temp_relation_vector = list(unpack(precision_string * embedding_dim, sockRecv(embedding_sock, precision_byte * embedding_dim)))
                #
                #   relation_vectors[relations[relation_id_temp] + '_v'] = compress(dumps(
                #       np.array(temp_relation_vector, dtype=np.float32), protocol=HIGHEST_PROTOCOL), 9)

                # 원소를 한 번에 받음 (릴레이션 한 번에)
                count_relation = int(unpack('!i', sockRecv(embedding_sock, 4))[0])
                relation_id_list = unpack('!' + 'i' * count_relation, sockRecv(embedding_sock, count_relation * 4))
                relation_vector_list = list(unpack(precision_string * count_relation * embedding_dim,
                    sockRecv(embedding_sock, precision_byte * embedding_dim * count_relation)))

                for _i in range(count_relation):

                    temp_relation_vector = relation_vector_list[_i * embedding_dim:(_i + 1) * embedding_dim]
                    relation_vectors[relations[relation_id_list[_i]] + '_v'] = compress(dumps(
                        np.array(temp_relation_vector, dtype=np.float32), protocol=HIGHEST_PROTOCOL), 9)

            except Exception as e:

                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

                if tempcount < 3:

                    printt('[error] worker > retry phase 3 (relation) - ' + worker_id)
                    printt('[error] worker > ' + str(e))
                    printt('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno))
                    # fsLog.write('[error] worker > retry phase 3 (relation) - ' + worker_id + '\n')
                    # fsLog.write('[error] worker > ' + str(e) + '\n')
                    # fsLog.write('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno) + '\n')

                else:

                    printt('[error] worker > failed phase 3 (relation) - ' + worker_id)
                    printt('[error] worker > ' + str(e))
                    printt('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno))
                    printt('[error] worker > return -1')
                    # fsLog.write('[error] worker > retry phase 3 (relation) - ' + worker_id + '\n')
                    # fsLog.write('[error] worker > ' + str(e) + '\n')
                    # fsLog.write('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno) + '\n')
                    # fsLog.write('[error] worker > return -1\n')
                    # fsLog.close()
                    sys.exit(-1)

                tempcount = tempcount + 1
                flag = 9876
                embedding_sock.send(pack('!i', flag))
                success = 0

            else:

                #printt('worker > phase 3 (relation) finished - ' + worker_id)
                #fsLog.write('worker > phase 3 (relation) finished - ' + worker_id + '\n')
                flag = 1234
                embedding_sock.send(pack('!i', flag))
                success = 1

        sockSaveTime = timeit.default_timer() - timeNow
        timeNow = timeit.default_timer()

        r.mset(relation_vectors)
        #printt('worker > relation_vectors updated - ' + worker_id)
        #printt('worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id)
        #fsLog.write('worker > relation_vectors updated - ' + worker_id + '\n')
        #fsLog.write('worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id + '\n')
        # fsLog.close()
        redisTime += timeit.default_timer() - timeNow

except Exception as e:

    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

    printt('[error] worker > exception occured in iteration - ' + worker_id)
    printt('[error] worker > ' + str(e))
    printt('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno))
    printt('[error] worker > return -1')
    # fsLog.write('[error] worker > exception occured in iteration - ' + str(worker_id) + '\n')
    # fsLog.write('[error] worker > ' + str(e) + '\n')
    # fsLog.write('[error] worker > exception occured in line ' + str(exc_tb.tb_lineno) + '\n')
    # fsLog.write('[error] worker > return -1\n')
    # fsLog.close()
    sys.exit(-1)


workerTotalTime = timeit.default_timer() - workerStart
modelRunTime = unpack('d', sockRecv(embedding_sock, 8))[0]
embedding_sock.close()

output_times = dict()
output_times["datamodel_sock"] = datamodelTime
output_times["socket_load"] = sockLoadTime
output_times["embedding"] = embeddingTime
output_times["model_run"] = modelRunTime
output_times["socket_save"] = sockSaveTime
output_times["redis"] = redisTime
output_times["worker_total"] = workerTotalTime
output_times = compress(dumps(output_times, protocol=HIGHEST_PROTOCOL), 9)
r.set("%s_%d" % (worker_id, cur_iter), output_times)

sys.exit(0)
