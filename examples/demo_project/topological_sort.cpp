#include <iostream>
#include <vector>
#include <queue>
#include <stack>

using namespace std;

class Graph {
private:
    int V; // 顶点数
    vector<vector<int>> adj; // 邻接表

public:
    Graph(int v) : V(v), adj(v) {}

    // 添加有向边 u -> v
    void addEdge(int u, int v) {
        adj[u].push_back(v);
    }

    // Kahn算法 (BFS) 拓扑排序
    vector<int> topologicalSortKahn() {
        vector<int> inDegree(V, 0);
        
        // 计算所有顶点的入度
        for (int u = 0; u < V; u++) {
            for (int v : adj[u]) {
                inDegree[v]++;
            }
        }
        
        // 将所有入度为0的顶点入队
        queue<int> q;
        for (int i = 0; i < V; i++) {
            if (inDegree[i] == 0) {
                q.push(i);
            }
        }
        
        vector<int> result;
        
        while (!q.empty()) {
            int u = q.front();
            q.pop();
            result.push_back(u);
            
            // 减少相邻顶点的入度
            for (int v : adj[u]) {
                inDegree[v]--;
                if (inDegree[v] == 0) {
                    q.push(v);
                }
            }
        }
        
        // 检查是否存在环
        if (result.size() != V) {
            cout << "图中存在环，无法进行拓扑排序" << endl;
            return {};
        }
        
        return result;
    }

    // DFS方法拓扑排序
    vector<int> topologicalSortDFS() {
        vector<bool> visited(V, false);
        stack<int> stk;
        
        // 对每个未访问的顶点调用DFS
        for (int i = 0; i < V; i++) {
            if (!visited[i]) {
                dfs(i, visited, stk);
            }
        }
        
        vector<int> result;
        while (!stk.empty()) {
            result.push_back(stk.top());
            stk.pop();
        }
        
        // 检查是否存在环（DFS会自动检测环吗？需要额外逻辑）
        // 这里假设图是DAG
        return result;
    }

private:
    void dfs(int u, vector<bool>& visited, stack<int>& stk) {
        visited[u] = true;
        
        for (int v : adj[u]) {
            if (!visited[v]) {
                dfs(v, visited, stk);
            }
        }
        
        // 后序遍历入栈
        stk.push(u);
    }
};

int main() {
    // 创建图示例
    Graph g(6);
    g.addEdge(5, 2);
    g.addEdge(5, 0);
    g.addEdge(4, 0);
    g.addEdge(4, 1);
    g.addEdge(2, 3);
    g.addEdge(3, 1);
    
    cout << "使用Kahn算法拓扑排序结果: ";
    vector<int> result1 = g.topologicalSortKahn();
    for (int v : result1) {
        cout << v << " ";
    }
    cout << endl;
    
    cout << "使用DFS算法拓扑排序结果: ";
    vector<int> result2 = g.topologicalSortDFS();
    for (int v : result2) {
        cout << v << " ";
    }
    cout << endl;
    
    return 0;
}