// 用药建议JavaScript
function executePrescription() {
    if (confirm('确定要执行此用药方案吗？')) {
        alert('用药方案已发送至无人机执行系统！');
        // 这里可以添加实际的执行逻辑
    }
}

function goBack() {
    window.location.href = '/mobile';
}



