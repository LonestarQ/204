#include <stdio.h>

int main() {
	int var = 5;    // ����һ�����ͱ���
	int *ptr;       // ����һ������ָ�����

	ptr = &var;     // ��var�ĵ�ַ����ָ�����ptr



	printf("Access value via ptr: %d\n", *ptr);


	printf("Access value via ptr: %d\n", ptr);

	printf("Value of var: %d\n", var);
	printf("sizeof: %d\n", sizeof(*ptr));
	return 0;
}
