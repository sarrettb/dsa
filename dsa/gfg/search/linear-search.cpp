#include <iostream>
#include <vector>

/* function to linear search */
int search(int arr[], int N, int X) {
    for (int i = 0; i < N; i++)
        if (arr[i] == X)
            return i + 1;
    return -1;
}

int main() {
    std::vector<std::vector<int>> test_points = { {1, 2, 3, 4, 5},
                                                  {5, 4, 3, 2, 1} } ;
    for (auto& t : test_points) {
        std::cout << "Position=" << search(t.data(), t.size(), 4) << std::endl;
    }
    return EXIT_SUCCESS;
}