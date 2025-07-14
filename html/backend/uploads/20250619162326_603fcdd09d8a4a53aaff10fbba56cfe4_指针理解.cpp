#include <stdio.h>

int main() {
	int var = 5;    // 声明一个整型变量
	int *ptr;       // 声明一个整型指针变量

	ptr = &var;     // 将var的地址赋给指针变量ptr



	printf("Access value via ptr: %d\n", *ptr);


	printf("Access value via ptr: %d\n", ptr);

	printf("Value of var: %d\n", var);
	printf("sizeof: %d\n", sizeof(*ptr));
	return 0;
}
