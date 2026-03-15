from django.test import TestCase

# Create your tests here.
import sys

def search(nums, target):
    left, right = 0, len(nums) - 1
    while left <= right:
        mid = (left + right) // 2
        if nums[mid] == target:
            return mid
        elif nums[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

if __name__ == "__main__":
    data = list(map(int, sys.stdin.read().strip().split()))
    if data:
        n = data[0]
        nums = data[1:1+n]
        target = data[1+n]
        print(search(nums, target))