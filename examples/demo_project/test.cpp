#include <vector>
#include <iostream>
#include <algorithm>
using namespace std;

class Solution {
public:
    int trap(vector<int>& height) {
        int n = height.size();
        if (n <= 2) return 0;
        
        int left = 0, right = n - 1;
        int left_max = 0, right_max = 0;
        int water = 0;
        
        while (left < right) {
            if (height[left] < height[right]) {
                if (height[left] >= left_max) {
                    left_max = height[left];
                } else {
                    water += left_max - height[left];
                }
                left++;
            } else {
                if (height[right] >= right_max) {
                    right_max = height[right];
                } else {
                    water += right_max - height[right];
                }
                right--;
            }
        }
        
        return water;
    }
};

int main() {
    Solution sol;
    
    // 测试用例 1: [0,1,0,2,1,0,1,3,2,1,2,1] -> 6
    vector<int> h1 = {0,1,0,2,1,0,1,3,2,1,2,1};
    cout << "Test 1: " << sol.trap(h1) << " (expected 6)" << endl;
    
    // 测试用例 2: [4,2,0,3,2,5] -> 9
    vector<int> h2 = {4,2,0,3,2,5};
    cout << "Test 2: " << sol.trap(h2) << " (expected 9)" << endl;

    return 0;
}
