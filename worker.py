# coding: utf-8
import os
from subprocess import Popen
from time import time
import logging
import numpy as np
import redis
import pickle
import sys
import socket
import timeit
import time as tt
import struct

chunk_data = sys.argv[1]
worker_id = sys.argv[2]
cur_iter = sys.argv[3]
embedding_dim = sys.argv[4]
learning_rate = sys.argv[5]
margin = sys.argv[6]
train_iter = sys.argv[7]
redis_ip_address = sys.argv[8]
root_dir = sys.argv[9]
data_root_id = sys.argv[10]
socket_port = sys.argv[11]
debugging = sys.argv[12]
logging.basicConfig(filename='%s/worker_%s.log' % (root_dir, worker_id), filemode='w', level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)

if debugging == 'yes':
    logging.basicConfig(filename='%s/master.log' %
                        root_dir, filemode='w', level=logging.DEBUG)
    logger = logging.getLogger()
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(handler)
    loggerOn = False

    def printt(str):

        global loggerOn

        print(str)

        if loggerOn:

            logger.warning(str + '\n')

    def handle_exception(exc_type, exc_value, exc_traceback):

        if issubclass(exc_type, KeyboardInterrupt):

            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.error("exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

elif debugging == 'no':
    
    def printt(str):
    
        print(str)

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
entities = pickle.loads(r.get('entities'))
relations = pickle.loads(r.get('relations'))
entity_id = r.mget(entities)
relation_id = r.mget(relations)
entities_initialized = r.mget([entity + '_v' for entity in entities])
relations_initialized = r.mget([relation + '_v' for relation in relations])

entity_id = {entities[i]: int(id_) for i, id_ in enumerate(entity_id)}
relation_id = {relations[i]: int(id_) for i, id_ in enumerate(relation_id)}

entities_initialized = [pickle.loads(v) for v in entities_initialized]
relations_initialized = [pickle.loads(v) for v in relations_initialized]

redisConnTime = timeit.default_timer() - workerStart
printt('[info] worker > redis server connection time : %f' % (redisConnTime))

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
        
        tt.sleep(1)
        trial = trial + 1
        printt('[error] worker > exception occured in worker <-> embedding')
        printt('[error] worker > ' + str(e))

    if trial == 5:

        printt('[error] worker > iteration ' + str(cur_iter) + ' failed - ' + worker_id)
        printt('[error] worker > return -1')
        sys.exit(-1)

trial = 0
while True:
    
    try:
        
        embedding_sock.connect(('0.0.0.0', int(socket_port)))
        break

    except Exception as e:
        
        tt.sleep(1)
        trial = trial + 1
        printt('[error] worker > exception occured in worker <-> embedding')
        printt('[error] worker > ' + str(e))

    if trial == 5:

        printt('[error] worker > iteration ' + str(cur_iter) + ' failed - ' + worker_id)
        printt('[error] worker > return -1')
        sys.exit(-1)

# printt('[info] worker > port number of ' + worker_id + ' = ' + socket_port)
# printt('[info] worker > socket connected (worker <-> embedding)')

# 파일로 로그를 저장하기 위한 부분
# fsLog = open(os.path.join(root_dir, 'logs/worker_log_' + worker_id + '_iter_' + cur_iter + '.txt'), 'w')
# fsLog.write('line 143 start\n')

# DataModel 생성자 -> GeometricModel load 메소드 -> GeometricModel save 메소드 순서로 통신
try:

    checksum = 0
    timeNow = timeit.default_timer()

    if int(cur_iter) % 2 == 0:
        # entity 전송 - DataModel 생성자
        chunk_anchor, chunk_entity = chunk_data.split('\n')
        chunk_anchor = chunk_anchor.split(' ')
        chunk_entity = chunk_entity.split(' ')

        if len(chunk_anchor) == 1 and chunk_anchor[0] == '':
            
            chunk_anchor = []

        while checksum != 1:

            embedding_sock.send(struct.pack('!i', len(chunk_anchor)))

            for iter_anchor in chunk_anchor:
                
                embedding_sock.send(struct.pack('!i', int(iter_anchor)))

            embedding_sock.send(struct.pack('!i', len(chunk_entity)))

            for iter_entity in chunk_entity:
                
                embedding_sock.send(struct.pack('!i', int(iter_entity)))

            checksum = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]

            if checksum == 1234:

                #printt('[info] worker > phase 1 finished - ' + worker_id)
                #fsLog.write('[info] worker > phase 1 finished - ' + worker_id + '\n')
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

        #printt('[info] worker > phase 1 : entity sent to DataModel finished')
        #fsLog.write('[info] worker > phase 1 : entity sent to DataModel finished\n')

    else:
        # relation 전송 - DataModel 생성자
        sub_graphs = pickle.loads(r.get('sub_g_{}'.format(worker_id)))
        embedding_sock.send(struct.pack('!i', len(sub_graphs)))

        while checksum != 1:

            for (head_id, relation_id_, tail_id) in sub_graphs:
                
                embedding_sock.send(struct.pack('!i', int(head_id)))
                embedding_sock.send(struct.pack('!i', int(relation_id_)))
                embedding_sock.send(struct.pack('!i', int(tail_id)))

            checksum = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]

            if checksum == 1234:

                #printt('[info] worker > phase 1 finished - ' + worker_id)
                #fsLog.write('[info] worker > phase 1 finished - ' + worker_id + '\n')
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

        #printt('[info] worker > phase 1 : relation sent to DataModel finished')
        #fsLog.write('[info] worker > phase 1 : relation sent to DataModel finished\n')

    datamodelTime = timeit.default_timer() - timeNow
    checksum = 0
    timeNow = timeit.default_timer()

    # entity_vector 전송 - GeometricModel load
    while checksum != 1:

        id_entity = dict()

        for i, vector in enumerate(entities_initialized):

            entity_name = str(entities[i])
            id_entity[entity_id[entity_name]] = entity_name
            #embedding_sock.send(struct.pack('!i', len(entity_name)))        # entity string 자체를 전송
            #embedding_sock.send(str.encode(entity_name))                    # entity string 자체를 전송


            embedding_sock.send(struct.pack('!i', entity_id[entity_name])) # entity id 를 int 로 전송


            for v in vector:

                embedding_sock.send(struct.pack('d', float(v)))

        checksum = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]

        if checksum == 1234:

            #printt('[info] worker > phase 2 (entity) finished - ' + worker_id)
            #fsLog.write('[info] worker > phase 2 (entity) finished - ' + worker_id + '\n')
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

    #printt('[info] worker > phase 2.1 : entity_vector sent to GeometricModel load function')
    #fsLog.write('[info] worker > phase 2.1 : entity_vector sent to GeometricModel load function\n')

    checksum = 0

    # relation_vector 전송 - GeometricModel load
    while checksum != 1:

        id_relation = dict()

        for i, relation in enumerate(relations_initialized):

            relation_name = str(relations[i])
            id_relation[relation_id[relation_name]] = relation_name
            #embedding_sock.send(struct.pack('!i', len(relation_name)))          # relation string 자체를 전송
            #embedding_sock.send(str.encode(relation_name))                      # relation string 자체를 전송

            embedding_sock.send(struct.pack('!i', relation_id[relation_name])) # relation id 를 int 로 전송

            for v in relation:

                embedding_sock.send(struct.pack('d', float(v)))

        checksum = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]
        #printt('[info] worker > received checksum = ' + str(checksum) + ' - ' + worker_id)
        #fsLog.write('[info] worker > received checksum = ' + str(checksum) + ' - ' + worker_id + '\n')

        if checksum == 1234:

            #printt('[info] worker > phase 2 (relation) finished - ' + worker_id)
            #fsLog.write('[info] worker > phase 2 (relation) finished - ' + worker_id + '\n')
            checksum = 1

        elif checksum == 9876:

            printt('[error] worker > retry phase 2 (relation) - worker.py - ' + worker_id)
            # fsLog.write('[error] worker > retry phase 2 (relation) - ' + worker_id + '\n')
            checksum = 0

        else:

            printt('[error] worker > unknown error in phase 2 (relation) - ' + worker_id)
            printt('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id)
            printt('[error] worker > return -1')
            # fsLog.write('[error] worker > unknown error in phase 2 (relation) - ' + worker_id + '\n')
            # fsLog.write('[error] worker > received checksum = ' + str(checksum) + ' - ' + worker_id + '\n')
            # fsLog.write('[error] worker > return -1\n')
            # fsLog.close()
            sys.exit(-1)

    sockLoadTime = timeit.default_timer() - timeNow
    timeNow = timeit.default_timer()

    #printt('[info] worker > phase 2.2 : relation_vector sent to GeometricModel load function')
    #fsLog.write('[info] worker > phase 2.2 : relation_vector sent to GeometricModel load function\n')

    del entities_initialized
    del relations_initialized

    tempcount = 0

    if int(cur_iter) % 2 == 0:

        success = 0

        while success != 1:

            try:        

                entity_vectors = dict()

                # 처리 결과를 받아옴 - GeometricModel save
                count_entity_data = sockRecv(embedding_sock, 4)
                embeddingTime = timeit.default_timer() - timeNow()
                
                if len(count_entity_data) != 4:
                    
                    printt('[error] worker > length of count_entity_data = ' + str(len(count_entity_data)))
                    printt('[error] worker > embedding_port = ' + socket_port)
                    # fsLog.write('[error] worker > length of count_entity_data = ' + str(len(count_entity_data)) + '\n')
                    # fsLog.write('[error] worker > embedding_port = ' + socket_port + '\n')
                
                count_entity = struct.unpack('!i', count_entity_data)[0]
                #printt('[info] worker > count_entity = ' + str(count_entity))
                #fsLog.write('[info] worker > count_entity = ' + str(count_entity) + '\n')

                for entity_idx in range(count_entity):
                    
                    temp_entity_vector = list()
                    
                    #entity_id_len = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]
                    #entity_id = embedding_sock.recv(entity_id_len).decode()


                    entity_id_temp = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]     # entity_id 를 int 로 받음
                    

                    for dim_idx in range(int(embedding_dim)):
                        
                        temp_entity_double = sockRecv(embedding_sock, 8)
                        
                        if len(temp_entity_double) != 8:
                            
                            printt('[error] worker > length of temp_entity_double = ' + str(len(temp_entity_double)))
                            # fsLog.write('[error] worker > length of temp_entity_double = ' + str(len(temp_entity_double)) + '\n')
                        
                        temp_entity = struct.unpack('d', temp_entity_double)[0]
                        temp_entity_vector.append(temp_entity)

                    #entity_vectors[entity_id + '_v'] = pickle.dumps(                            # string 일 때
                    #    np.array(temp_entity_vector), protocol=pickle.HIGHEST_PROTOCOL)
                    entity_vectors[id_entity[entity_id_temp] + '_v'] = pickle.dumps(                      # int 일 때
                        np.array(temp_entity_vector), protocol=pickle.HIGHEST_PROTOCOL)

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
                embedding_sock.send(struct.pack('!i', flag))
                success = 0

            else:

                #printt('[info] worker > phase 3 (entity) finished - ' + worker_id)
                #fsLog.write('[info] worker > phase 3 (entity) finished - ' + worker_id + '\n')
                flag = 1234
                embedding_sock.send(struct.pack('!i', flag))
                success = 1

        sockSaveTime = timeit.default_timer() - timeNow
        timeNow = timeit.default_timer()
        
        r.mset(entity_vectors)
        #printt('[info] worker > entity_vectors updated - ' + worker_id)
        #printt('[info] worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id)
        #fsLog.write('[info] worker > entity_vectors updated - ' + worker_id + '\n')
        #fsLog.write('[info] worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id + '\n')
        #fsLog.close()
        redisTime = timeit.default_timer() - timeNow
        tt.sleep(1)
        sys.exit(0)

    else:

        success = 0

        while success != 1:

            try:    

                relation_vectors = dict()

                # 처리 결과를 받아옴 - GeometricModel save
                count_relation_data = sockRecv(embedding_sock, 4)
                count_relation = struct.unpack('!i', count_relation_data)[0]
                #printt('[info] worker > count_relation is ' + str(count_relation))
                #fsLog.write('[info] worker > count_relation is ' + str(count_relation) + '\n')

                for relation_idx in range(count_relation):
                    
                    temp_relation_vector = list()
                    #relation_id_len = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]
                    #relation_id = embedding_sock.recv(relation_id_len).decode()


                    relation_id_temp = struct.unpack('!i', sockRecv(embedding_sock, 4))[0]   # relation_id 를 int 로 받음


                    for dim_idx in range(int(embedding_dim)):
                        
                        temp_relation_double = sockRecv(embedding_sock, 8)
                        
                        if len(temp_relation_double) != 8:
                            
                            printt('[info] worker > length of temp_relation_double = ' + str(len(temp_relation_double)))
                            #fsLog.write('[info] worker > length of temp_relation_double = ' + str(len(temp_relation_double)) + '\n')

                        temp_relation = struct.unpack('d', temp_relation_double)[0]
                        temp_relation_vector.append(temp_relation)

                    #relation_vectors[relation_id + '_v'] = pickle.dumps(                        # string 일 때
                    #    np.array(temp_relation_vector), protocol=pickle.HIGHEST_PROTOCOL)
                    relation_vectors[id_relation[relation_id_temp] + '_v'] = pickle.dumps(                  # int 일 때
                        np.array(temp_relation_vector), protocol=pickle.HIGHEST_PROTOCOL)
        
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
                embedding_sock.send(struct.pack('!i', flag))
                success = 0

            else:

                #printt('[info] worker > phase 3 (relation) finished - ' + worker_id)
                #fsLog.write('[info] worker > phase 3 (relation) finished - ' + worker_id + '\n')
                flag = 1234
                embedding_sock.send(struct.pack('!i', flag))
                success = 1

        sockSaveTime = timeit.default_timer() - timeNow
        timeNow = timeit.default_timer()        

        r.mset(relation_vectors)
        #printt('[info] worker > relation_vectors updated - ' + worker_id)
        #printt('[info] worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id)
        #fsLog.write('[info] worker > relation_vectors updated - ' + worker_id + '\n')
        #fsLog.write('[info] worker > iteration ' + str(cur_iter) + ' finished - ' + worker_id + '\n')
        # fsLog.close()
        redisTime = timeit.default_timer() - timeNow
        tt.sleep(1)
        sys.exit(0)

except Exception as e:

    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

    printt('[error] worker > exception occured in iteration - ' + str(worker_id))
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

resultDict = {'worker_' + str(worker_id) + '_iter_' + str(cur_iter) : dict()}
resultDict['worker_' + str(worker_id) + '_iter_' + str(cur_iter)]["\n== redis_conn_time = {}\n"] = redisConnTime
resultDict['worker_' + str(worker_id) + '_iter_' + str(cur_iter)]["\n== datamodel_sock_time = {}\n"] = datamodelTime
resultDict['worker_' + str(worker_id) + '_iter_' + str(cur_iter)]["\n== socket_load_time = {}\n"] = sockLoadTime
resultDict['worker_' + str(worker_id) + '_iter_' + str(cur_iter)]["\n== embedding_time = {}\n"] = embeddingTime
resultDict['worker_' + str(worker_id) + '_iter_' + str(cur_iter)]["\n== socket_save_time = {}\n"] = sockSaveTime
resultDict['worker_' + str(worker_id) + '_iter_' + str(cur_iter)]["\n== redis_time = {}\n"] = redisTime
resultDict['worker_' + str(worker_id) + '_iter_' + str(cur_iter)]["\n== worker_total_time = {}\n"] = workerTotalTime
r.set(resultDict)