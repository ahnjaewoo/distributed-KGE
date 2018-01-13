#include "Import.hpp"
#include "DetailedConfig.hpp"
// #include "LatentModel.hpp"
// #include "OrbitModel.hpp"
#include "Task.hpp"
#include <omp.h>
#include <sys/time.h>


#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>


void getParams(int argc, char* argv[], int& dim, double& alpha, double& training_threshold, int& worker_num, int& master_epoch, int& fd);

// 400s for each experiment.
int main(int argc, char* argv[])
{
	srand(time(nullptr));
	//omp_set_num_threads(6);

	Model* model = nullptr;
	int use_socket = 0;

	//first read the txt file and load the model
	//read dimension, LR, margin for parameters
	int dim = 20;
	double alpha = 0.01;
	double training_threshold = 2;
	int worker_num = 0;
	int master_epoch = 0;
	int fd = 0;
	

	if (use_socket)
	{
		// embedding.cpp is server
		// worker.py is client
		// IP addr / port are from master.py
		int flag_iter;
		int end_iter;
		unsigned int len;
		int embedding_sock, worker_sock;
		struct sockaddr_in embedding_addr;
		struct sockaddr_in worker_addr;

		getParams(argc, argv, dim, alpha, training_threshold, worker_num, master_epoch, fd);

		bzero((char *)&embedding_addr, sizeof(embedding_addr));
		embedding_addr.sin_family = AF_INET;
		embedding_addr.sin_addr.s_addr = inet_addr("0.0.0.0");
		embedding_addr.sin_port = htons(49900 + worker_num);

		// create socket and check it is valid
		if ((embedding_sock = socket(PF_INET, SOCK_STREAM, 0)) < 0){

			return -1;
		}

		if (bind(embedding_sock, (struct sockaddr *)&embedding_addr, sizeof(embedding_addr)) < 0){

			return -1;
		}

		if (listen(embedding_sock, 1) < 0){

			return -1;
		}

		while (1){

			len = sizeof(worker_addr);

			if ((worker_sock = accept(embedding_sock, (struct sockaddr *)&worker_addr, &len)) < 0){

				return -1;
			}

			while (1){

				if (recv(worker_sock, &flag_iter, sizeof(flag_iter), 0) < 0){

					close(worker_sock);
					break;
				}

				if (ntohl(flag_iter) == 1){

					close(worker_sock);
					break;
				}


				// receive data
				if(recv(worker_sock, &worker_num, sizeof(worker_num), 0) < 0){

					close(worker_sock);
					break;
				}

				if(recv(worker_sock, &master_epoch, sizeof(master_epoch), 0) < 0){

					close(worker_sock);
					break;
				}

				if(recv(worker_sock, &dim, sizeof(dim), 0) < 0){

					close(worker_sock);
					break;
				}

				if(recv(worker_sock, &alpha, sizeof(alpha), 0) < 0){

					close(worker_sock);
					break;
				}

				if(recv(worker_sock, &training_threshold, sizeof(training_threshold), 0) < 0){

					close(worker_sock);
					break;
				}

				worker_num = ntohl(worker_num);
				master_epoch = ntohl(master_epoch);
				dim = ntohl(dim);


				model = new TransE(FB15K, LinkPredictionTail, report_path, dim, alpha, training_threshold, true, worker_num, master_epoch, fd);
				//model->load(worker_sock);

				//after training, put entities and relations into txt file
				model->save(to_string(worker_num));
				//model->save(worker_sock);


				end_iter = 0;
				end_iter = htonl(end_iter);
				send(worker_sock, &end_iter, sizeof(end_iter), 0);

				//calculating testing time
				struct timeval after, before;
				gettimeofday(&before, NULL);

				model->test();

				gettimeofday(&after, NULL);
				cout << "testing test_data time :  " << after.tv_sec + after.tv_usec/1000000.0 - before.tv_sec - before.tv_usec/1000000.0 << "seconds" << endl;
				
				delete model;
				// close(worker_sock);
				// reconnect to worker.py
				// TODO : model->save using socket communication
			}
		}
	}
	else 
	{
		// Model* model = nullptr;
		getParams(argc, argv, dim, alpha, training_threshold, worker_num, master_epoch, fd);

		//model = new TransE(FB15K, LinkPredictionTail, report_path, dim, alpha, training_threshold, false);
		model = new TransE(FB15K, LinkPredictionTail, report_path, dim, alpha, training_threshold, true, worker_num, master_epoch, fd);

		//calculating testing time
		struct timeval after, before;
		gettimeofday(&before, NULL);
		model->test();
		gettimeofday(&after, NULL);
		cout << "testing test_data time :  " << after.tv_sec + after.tv_usec/1000000.0 - before.tv_sec - before.tv_usec/1000000.0 << "seconds" << endl;
		delete model;
	}

	return 0;
}

void getParams(int argc, char* argv[], int& dim, double& alpha, double& training_threshold, int& worker_num, int& master_epoch, int& fd)
{
	if (argc == 2)
	{
		// very big problem for scaling!!!!!!!!!!!!!!!!!!!!!!!!!!!
		string worker = argv[1];
		worker_num = worker.back() - '0';
	}
	if (argc == 3)
	{
		string worker = argv[1];
                worker_num = worker.back() - '0';
		master_epoch = atoi(argv[2]);
	}
	if (argc == 4)
	{
		string worker = argv[1];
                worker_num = worker.back() - '0';
		master_epoch = atoi(argv[2]);
		dim = atoi(argv[3]);
	}
	if (argc == 5)
	{
		string worker = argv[1];
                worker_num = worker.back() - '0';
		master_epoch = atoi(argv[2]);
		dim = atoi(argv[3]);
		alpha = atof(argv[4]);
	}
	if (argc == 6)
	{
		string worker = argv[1];
                worker_num = worker.back() - '0';
		master_epoch = atoi(argv[2]);
		dim = atoi(argv[3]);
		alpha = atof(argv[4]);
		training_threshold = atof(argv[5]);
	}
	if (argc == 7)
	{
		string worker = argv[1];
		worker_num = worker.back() - '0';
		master_epoch = atoi(argv[2]);
		dim = atoi(argv[3]);
		alpha = atof(argv[4]);
		training_threshold = atof(argv[5]);
		fd = atoi(argv[7]);
	}
}  
