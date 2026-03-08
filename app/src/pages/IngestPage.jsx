import { useState, useContext, useEffect } from 'react'
import { Layout, Button, Typography, Steps, Upload, Card, message, Progress, Space } from 'antd'
import { InboxOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { ThemeContext } from '../main'
import { useNavigate } from 'react-router-dom'

const { Header, Content } = Layout
const { Title, Text } = Typography
const { Dragger } = Upload

export default function IngestPage() {
    const { isDark } = useContext(ThemeContext)
    const navigate = useNavigate()

    const [currentStep, setCurrentStep] = useState(0)
    const [taskId, setTaskId] = useState(null)
    const [taskStatus, setTaskStatus] = useState(null)

    useEffect(() => {
        let interval;
        if (taskId && currentStep > 0 && taskStatus?.state !== 'COMPLETED' && taskStatus?.state !== 'FAILED') {
            interval = setInterval(async () => {
                try {
                    const res = await fetch(`http://localhost:3001/api/worker/status/${taskId}`)
                    const data = await res.json()
                    setTaskStatus(data)
                    if (data.state === 'COMPLETED') {
                        message.success('Pipeline finished! UMAP updated.')
                        setCurrentStep(3)
                    } else if (data.state === 'FAILED') {
                        message.error(`Pipeline failed: ${data.error}`)
                    }
                } catch (err) {
                    console.error(err)
                }
            }, 1000)
        }
        return () => clearInterval(interval)
    }, [taskId, currentStep, taskStatus?.state])

    // Dummy upload props for now until the backend is wired up
    const uploadProps = {
        name: 'file',
        multiple: false,
        action: 'http://localhost:3001/api/worker/ingest',
        onChange(info) {
            const { status } = info.file;
            if (status === 'done') {
                message.success(`${info.file.name} uploaded successfully.`);
                if (info.file.response && info.file.response.task_id) {
                    setTaskId(info.file.response.task_id)
                    setCurrentStep(1)
                    setTaskStatus({ progress: 0, state: 'QUEUED' })
                }
            } else if (status === 'error') {
                message.error(`${info.file.name} file upload failed.`);
            }
        },
        onDrop(e) {
            console.log('Dropped files', e.dataTransfer.files);
        },
    };

    const steps = [
        { title: 'Upload Data', description: 'FASTA/CSV format' },
        { title: 'Embed', description: 'ESM-2 processing' },
        { title: 'UMAP Projection', description: 'Iterative 5D manifold' },
        { title: 'Done', description: 'Ready to view' }
    ]

    return (
        <Layout style={{ height: '100vh', overflow: 'hidden' }}>
            <Header style={{
                background: 'var(--bg-surface)',
                borderBottom: '1px solid var(--border)',
                padding: '0 20px',
                display: 'flex', alignItems: 'center', gap: 20
            }}>
                <Button
                    icon={<ArrowLeftOutlined />}
                    type="text"
                    onClick={() => navigate('/')}
                    style={{ color: 'var(--text-main)' }}
                >
                    Back to Explorer
                </Button>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-main)' }}>
                    Data Ingestion Pipeline
                </div>
            </Header>

            <Content style={{ padding: '40px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '30px', overflowY: 'auto' }}>
                <div style={{ width: '100%', maxWidth: 800 }}>
                    <Steps current={currentStep} items={steps} />
                </div>

                <Card
                    style={{ width: '100%', maxWidth: 800, background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
                    bordered={false}
                >
                    {currentStep === 0 && (
                        <div style={{ textAlign: 'center', padding: '20px 0' }}>
                            <Title level={4} style={{ color: 'var(--text-main)' }}>Import Lab Data</Title>
                            <Text style={{ color: 'var(--text-dim)', display: 'block', marginBottom: '24px' }}>
                                Upload a CSV containing a 'CDR3b' column or a FASTA file.
                                The pipeline will compute the 1280-dimensional ESM-2 embedding and map it to the 5D UMAP manifold instantaneously.
                            </Text>

                            <Dragger {...uploadProps} style={{ background: 'var(--bg-base)', padding: '40px' }}>
                                <p className="ant-upload-drag-icon">
                                    <InboxOutlined style={{ color: 'var(--color-primary)' }} />
                                </p>
                                <p className="ant-upload-text" style={{ color: 'var(--text-main)' }}>Click or drag file to this area to ingest</p>
                                <p className="ant-upload-hint" style={{ color: 'var(--text-dim)' }}>
                                    Support for a single or bulk upload. Strictly prohibit uploading company data or other band files.
                                </p>
                            </Dragger>
                        </div>
                    )}

                    {currentStep > 0 && (
                        <div style={{ textAlign: 'center', padding: '40px 0' }}>
                            <Title level={4} style={{ color: 'var(--text-main)', marginBottom: '8px' }}>
                                {taskStatus?.state === 'COMPLETED' ? 'Dataset Ingested!' : 'Processing in Background...'}
                            </Title>
                            <Text style={{ color: 'var(--text-dim)', display: 'block', marginBottom: '30px' }}>
                                {taskStatus?.state === 'COMPLETED'
                                    ? 'All TCRs have been successfully passed through ESM-2 and mapped into the 5-dimensional UMAP projection.'
                                    : 'Your job was submitted to the async worker. Validating sequences, running inference, and mapping coordinates.'}
                            </Text>

                            <Progress
                                type="circle"
                                percent={taskStatus ? Math.round(taskStatus.progress * 100) : 0}
                                status={taskStatus?.state === 'FAILED' ? 'exception' : taskStatus?.state === 'COMPLETED' ? 'success' : 'active'}
                                strokeColor="var(--color-primary)"
                            />

                            {taskStatus?.state === 'COMPLETED' && (
                                <div style={{ marginTop: '30px' }}>
                                    <Button type="primary" size="large" onClick={() => navigate('/')}>
                                        View in Explorer
                                    </Button>
                                </div>
                            )}
                            {taskStatus?.state === 'FAILED' && (
                                <div style={{ marginTop: '20px', color: '#ff4d4f' }}>
                                    Error: {taskStatus.error}
                                </div>
                            )}
                        </div>
                    )}
                </Card>
            </Content>
        </Layout>
    )
}
